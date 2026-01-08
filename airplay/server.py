# -*- coding: utf-8 -*-
"""
AirPlay server wrapper that monitors uxplay and publishes session events via ZMQ.
"""

import logging
import os
import re
import signal
import subprocess
import sys
import threading
from time import sleep

import redis
import zmq

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('airplay')

# AirPlay session states
STATE_IDLE = 'idle'
STATE_CONNECTED = 'connected'
STATE_STREAMING = 'streaming'


class AirPlayServer:
    """
    Wrapper around uxplay that monitors its output and publishes
    session state changes via ZMQ.
    """

    def __init__(self):
        self.device_name = os.getenv('AIRPLAY_NAME', 'Checkin Cast')
        self.zmq_server_url = os.getenv(
            'ZMQ_SERVER_URL', 'tcp://checkin-server:10001'
        )
        self.audio_output = os.getenv('AUDIO_OUTPUT', 'hdmi')
        self.resolution = os.getenv('AIRPLAY_RESOLUTION', '1920x1080')
        self.framerate = os.getenv('AIRPLAY_FRAMERATE', '30')

        self.process = None
        self.state = STATE_IDLE
        self.running = False
        self.client_name = None
        self.restart_requested = False
        self.enabled = True  # Can be toggled via Redis command

        # Connect to Redis to read settings and listen for updates
        self.redis = redis.Redis(host='127.0.0.1', port=6379, decode_responses=True)
        self._load_settings_from_redis()

        # ZMQ publisher for session events
        self.context = zmq.Context()
        self.publisher = self.context.socket(zmq.PUB)
        self.publisher.connect(self.zmq_server_url.replace(':10001', ':10002'))
        sleep(0.5)  # Allow ZMQ to establish connection

        # Also create a push socket for direct viewer communication
        self.push_socket = self.context.socket(zmq.PUSH)
        self.push_socket.setsockopt(zmq.LINGER, 0)
        self.push_socket.connect('tcp://checkin-server:5559')
        sleep(0.5)

    def _load_settings_from_redis(self):
        """Load AirPlay settings from Redis if available."""
        try:
            name = self.redis.get('airplay_name')
            if name:
                self.device_name = name
                logger.info(f'Loaded AirPlay name from Redis: {name}')
        except redis.RedisError as e:
            logger.warning(f'Could not load settings from Redis: {e}')

    def _start_command_listener(self):
        """Start a thread to listen for restart commands via Redis pubsub."""
        def listener():
            try:
                pubsub = self.redis.pubsub()
                pubsub.subscribe('airplay_cmd')
                logger.info('Subscribed to airplay_cmd channel')

                for message in pubsub.listen():
                    if message['type'] == 'message':
                        cmd = message['data']
                        logger.info(f'Received command: {cmd}')
                        if cmd == 'restart':
                            self._load_settings_from_redis()
                            self.restart_requested = True
                            self.stop()
                        elif cmd == 'stop':
                            self.enabled = False
                            self.stop()
                        elif cmd == 'start':
                            self.enabled = True
                            self._load_settings_from_redis()
                            self.restart_requested = True
                            if not self.running:
                                # Will be started by main loop
                                pass
            except redis.RedisError as e:
                logger.error(f'Redis listener error: {e}')

        thread = threading.Thread(target=listener, daemon=True)
        thread.start()

    def _build_command(self):
        """Build the uxplay command with appropriate arguments."""
        # Don't specify resolution - let client decide dynamically
        cmd = [
            'uxplay',
            '-n', self.device_name,
            '-nh',  # Don't append hostname to device name
            '-fps', self.framerate,
            '-vs', 'kmssink',  # Output to KMS for fullscreen
            '-fs',  # Force fullscreen
            '-reset', '0',  # Never timeout on silence
        ]

        # Audio output configuration
        if self.audio_output == 'hdmi':
            cmd.extend(['-as', 'alsasink device=hw:0'])
        elif self.audio_output == 'headphones':
            cmd.extend(['-as', 'alsasink device=hw:1,0'])
        else:
            cmd.extend(['-as', 'alsasink'])

        return cmd

    def _publish_state(self, state, client_name=None):
        """Publish state change via ZMQ."""
        self.state = state
        self.client_name = client_name

        message = {
            'type': 'airplay_state',
            'state': state,
            'client_name': client_name,
        }

        try:
            # Publish to subscriber (for websocket server)
            self.publisher.send_json(message)
            logger.info(f'Published state: {state}, client: {client_name}')

            # Also push directly for viewer
            self.push_socket.send_json(message, flags=zmq.NOBLOCK)
        except zmq.ZMQError as e:
            logger.error(f'Failed to publish state: {e}')

    def _monitor_output(self):
        """Monitor uxplay stdout/stderr for session events."""
        # Patterns to detect session state
        connect_pattern = re.compile(r'Connection from .* \((.+)\)')
        stream_start_pattern = re.compile(r'Starting video stream')
        stream_stop_pattern = re.compile(r'Video stream stopped|Connection closed')

        while self.running and self.process:
            line = self.process.stderr.readline()
            if not line:
                if self.process.poll() is not None:
                    break
                continue

            line = line.decode('utf-8', errors='replace').strip()
            logger.debug(f'uxplay: {line}')

            # Check for connection
            match = connect_pattern.search(line)
            if match:
                client = match.group(1)
                self._publish_state(STATE_CONNECTED, client)
                continue

            # Check for stream start
            if stream_start_pattern.search(line):
                self._publish_state(STATE_STREAMING, self.client_name)
                continue

            # Check for stream stop / disconnect
            if stream_stop_pattern.search(line):
                self._publish_state(STATE_IDLE, None)

    def start(self):
        """Start the AirPlay server."""
        if self.running:
            logger.warning('AirPlay server already running')
            return

        logger.info(f'Starting AirPlay server as "{self.device_name}"')
        self.running = True

        cmd = self._build_command()
        logger.info(f'Command: {" ".join(cmd)}')

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid
            )

            # Start output monitor thread
            monitor_thread = threading.Thread(
                target=self._monitor_output,
                daemon=True
            )
            monitor_thread.start()

            logger.info(f'AirPlay server started (PID: {self.process.pid})')
            self._publish_state(STATE_IDLE)

            # Wait for process to complete
            self.process.wait()

        except Exception as e:
            logger.error(f'Failed to start AirPlay server: {e}')
            self.running = False
            raise
        finally:
            self.running = False
            self._publish_state(STATE_IDLE)

    def stop(self):
        """Stop the AirPlay server."""
        if not self.running or not self.process:
            return

        logger.info('Stopping AirPlay server')
        self.running = False

        try:
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass

        self._publish_state(STATE_IDLE)
        logger.info('AirPlay server stopped')

    def cleanup(self):
        """Clean up ZMQ resources."""
        self.stop()
        self.publisher.close()
        self.push_socket.close()
        self.context.term()


def main():
    """Main entry point for the AirPlay server."""
    server = AirPlayServer()
    server._start_command_listener()

    def signal_handler(signum, frame):
        logger.info(f'Received signal {signum}, shutting down...')
        server.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    while True:
        try:
            if server.enabled:
                server.start()
                # If we got here due to a restart request, continue the loop
                if server.restart_requested:
                    server.restart_requested = False
                    logger.info('Restarting AirPlay server with new settings...')
                    continue
            else:
                # AirPlay is disabled, just wait
                logger.info('AirPlay server disabled, waiting...')
                server._publish_state(STATE_IDLE)
                while not server.enabled:
                    sleep(1)
                logger.info('AirPlay server re-enabled')
        except Exception as e:
            logger.error(f'AirPlay server error: {e}')
        sleep(5)  # Wait before retry


if __name__ == '__main__':
    main()
