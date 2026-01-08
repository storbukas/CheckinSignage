#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Native AirPlay server that runs uxplay directly on the host.
Reads settings from Redis and restarts when settings change.
"""

import logging
import os
import signal
import subprocess
import sys
import threading
from configparser import ConfigParser
from pathlib import Path
from time import sleep

import redis

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('airplay-native')

# Default settings
DEFAULT_NAME = 'Checkin Cast'
DEFAULT_RESOLUTION = '1920x1080'
DEFAULT_FRAMERATE = '30'
DEFAULT_AUDIO_OUTPUT = 'hdmi'


class NativeAirPlayServer:
    """
    Native AirPlay server using uxplay directly on the host.
    """

    def __init__(self):
        self.process = None
        self.running = False
        self.restart_requested = False

        # Connect to Redis
        self.redis = redis.Redis(host='127.0.0.1', port=6379, decode_responses=True)

        # Load settings
        self.device_name = DEFAULT_NAME
        self.resolution = DEFAULT_RESOLUTION
        self.framerate = DEFAULT_FRAMERATE
        self.audio_output = DEFAULT_AUDIO_OUTPUT

        self._load_settings()

    def _load_settings(self):
        """Load settings from Redis and config file."""
        # Try Redis first
        try:
            name = self.redis.get('airplay_name')
            if name:
                self.device_name = name
                logger.info(f'Loaded AirPlay name from Redis: {name}')
                return
        except redis.RedisError as e:
            logger.warning(f'Could not read from Redis: {e}')

        # Fall back to config file
        config_path = Path.home() / '.screenly' / 'screenly.conf'
        if config_path.exists():
            try:
                config = ConfigParser()
                config.read(config_path)
                if config.has_option('airplay', 'airplay_name'):
                    self.device_name = config.get('airplay', 'airplay_name')
                    logger.info(f'Loaded AirPlay name from config: {self.device_name}')
                if config.has_option('viewer', 'audio_output'):
                    self.audio_output = config.get('viewer', 'audio_output')
            except Exception as e:
                logger.warning(f'Could not read config file: {e}')

    def _build_command(self):
        """Build the uxplay command."""
        width, height = self.resolution.split('x')

        cmd = [
            '/usr/local/bin/uxplay',
            '-n', self.device_name,
            '-nh',  # Don't append hostname
            '-s', f'{width}x{height}',
            '-fps', self.framerate,
        ]

        # Audio output - use ALSA for headless Pi
        # hw:0 = first HDMI output, hw:1 = second HDMI output
        if self.audio_output == 'hdmi':
            cmd.extend(['-as', 'alsasink device=hw:0'])
        elif self.audio_output == 'hdmi2':
            cmd.extend(['-as', 'alsasink device=hw:1'])
        else:
            cmd.extend(['-as', 'alsasink'])

        return cmd

    def _publish_state(self, state, client_name=None):
        """Publish state to Redis."""
        try:
            self.redis.set('airplay_state', state)
            if client_name:
                self.redis.set('airplay_client', client_name)
            else:
                self.redis.delete('airplay_client')
            logger.info(f'State: {state}, client: {client_name}')
        except redis.RedisError as e:
            logger.warning(f'Could not publish state: {e}')

    def _start_command_listener(self):
        """Listen for restart commands via Redis pubsub."""
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
                            self._load_settings()
                            self.restart_requested = True
                            self.stop()
            except redis.RedisError as e:
                logger.error(f'Redis listener error: {e}')
            except Exception as e:
                logger.error(f'Listener error: {e}')

        thread = threading.Thread(target=listener, daemon=True)
        thread.start()

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
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid
            )

            logger.info(f'AirPlay server started (PID: {self.process.pid})')
            self._publish_state('idle')

            # Monitor output for connection events
            while self.running and self.process:
                line = self.process.stdout.readline()
                if not line:
                    if self.process.poll() is not None:
                        break
                    continue

                line = line.decode('utf-8', errors='replace').strip()
                if line:
                    logger.debug(f'uxplay: {line}')

                    # Detect connection events
                    if 'connection from' in line.lower():
                        self._publish_state('connected')
                    elif 'mirror started' in line.lower() or 'video stream' in line.lower():
                        self._publish_state('streaming')
                    elif 'connection closed' in line.lower() or 'disconnected' in line.lower():
                        self._publish_state('idle')

        except Exception as e:
            logger.error(f'Failed to start AirPlay server: {e}')
            self.running = False
            raise
        finally:
            self.running = False
            self._publish_state('idle')

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

        self._publish_state('idle')
        logger.info('AirPlay server stopped')


def main():
    """Main entry point."""
    server = NativeAirPlayServer()
    server._start_command_listener()

    def signal_handler(signum, frame):
        logger.info(f'Received signal {signum}, shutting down...')
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    while True:
        try:
            server.start()
            if server.restart_requested:
                server.restart_requested = False
                logger.info('Restarting with new settings...')
                continue
        except Exception as e:
            logger.error(f'AirPlay server error: {e}')
        sleep(5)


if __name__ == '__main__':
    main()
