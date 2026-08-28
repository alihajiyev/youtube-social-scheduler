#!/bin/sh
if [ -n "$YOUTUBE_COOKIES_B64" ]; then
  echo "$YOUTUBE_COOKIES_B64" | base64 -d > /tmp/cookies.json 2>/dev/null
  if [ -s /tmp/cookies.json ]; then
    export COOKIE_PATH=/tmp/cookies.json
    echo "YouTube cookies loaded"
  else
    echo "Failed to decode cookies"
  fi
fi
exec node src/cobalt
