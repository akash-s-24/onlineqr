import time
import threading
from functools import wraps
from flask import request, jsonify, render_template, current_app, make_response


class SlidingWindowLimiter:
    """
    Thread-safe, high-performance in-memory sliding window rate limiter.
    Zero external dependencies, automatic stale entry eviction, proxy-aware IP resolution.
    """
    def __init__(self):
        self._lock = threading.Lock()
        # storage: { key: [timestamp1, timestamp2, ...] }
        self._windows = {}
        self._last_pruned = time.time()

    def get_client_ip(self):
        """
        Extract client IP address safely, taking into account X-Forwarded-For
        when running behind reverse proxies (Render, AWS ALB, Cloudflare, etc.).
        """
        forwarded = request.headers.get('X-Forwarded-For')
        if forwarded:
            ip = forwarded.split(',')[0].strip()
            if ip:
                return ip
        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip.strip()
        return request.remote_addr or '127.0.0.1'

    def is_allowed(self, key, limit, period_seconds):
        """
        Check if request under `key` is allowed within `limit` hits per `period_seconds`.
        Returns (is_allowed: bool, remaining: int, reset_epoch: int, retry_after: int).
        """
        now = time.time()
        with self._lock:
            # Periodic cleanup of keys inactive for more than 10 minutes
            if now - self._last_pruned > 600:
                self._prune_stale_keys(now)
                self._last_pruned = now

            timestamps = self._windows.get(key, [])
            cutoff = now - period_seconds
            # Keep only timestamps within the sliding window
            valid_timestamps = [ts for ts in timestamps if ts > cutoff]

            if len(valid_timestamps) < limit:
                valid_timestamps.append(now)
                self._windows[key] = valid_timestamps
                remaining = max(0, limit - len(valid_timestamps))
                reset_epoch = int(now + period_seconds)
                return True, remaining, reset_epoch, 0
            else:
                self._windows[key] = valid_timestamps
                oldest_in_window = valid_timestamps[0]
                retry_after = max(1, int(period_seconds - (now - oldest_in_window)))
                reset_epoch = int(oldest_in_window + period_seconds)
                return False, 0, reset_epoch, retry_after

    def _prune_stale_keys(self, now):
        stale_threshold = now - 600
        keys_to_delete = [
            k for k, timestamps in self._windows.items()
            if not timestamps or timestamps[-1] < stale_threshold
        ]
        for k in keys_to_delete:
            del self._windows[k]

    def reset(self):
        """Clear all rate limit tracking."""
        with self._lock:
            self._windows.clear()


# Global singleton instance
limiter = SlidingWindowLimiter()


def rate_limit(limit=15, period=60, methods=None, key_func=None, message="Too many requests."):
    """
    Decorator to apply sliding-window rate limiting to a Flask endpoint.
    - limit: maximum allowed requests in the time period
    - period: duration in seconds (default 60s)
    - methods: optional list of HTTP methods to throttle (e.g. ['POST']). If None, throttles all methods.
    - key_func: optional custom function to derive bucket key (defaults to endpoint:client_ip)
    - message: user-facing message when 429 is reached
    """
    if methods:
        target_methods = {m.upper() for m in methods}
    else:
        target_methods = None

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Check if this HTTP method should be throttled
            if target_methods and request.method not in target_methods:
                return f(*args, **kwargs)

            # Bypass during automated test suites unless explicitly testing rate limits
            if current_app.config.get('TESTING') and not current_app.config.get('TESTING_RATE_LIMITER'):
                return f(*args, **kwargs)

            ip = limiter.get_client_ip()
            key = key_func(ip) if key_func else f"{request.endpoint or request.path}:{ip}"

            allowed, remaining, reset_epoch, retry_after = limiter.is_allowed(key, limit, period)

            if not allowed:
                is_api = request.is_json or request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json'
                if is_api:
                    response = jsonify({
                        'status': 'error',
                        'message': f"{message} Please wait {retry_after} seconds before trying again.",
                        'code': 429,
                        'retry_after': retry_after
                    })
                    res = make_response(response, 429)
                else:
                    html_content = render_template(
                        'base.html',
                        title='Too Many Requests',
                        error_code=429,
                        error_message=f"{message} Please wait {retry_after} seconds before trying again."
                    )
                    res = make_response(html_content, 429)

                res.headers['Retry-After'] = str(retry_after)
                res.headers['X-RateLimit-Limit'] = str(limit)
                res.headers['X-RateLimit-Remaining'] = '0'
                res.headers['X-RateLimit-Reset'] = str(reset_epoch)
                return res

            response = f(*args, **kwargs)

            # Add informative rate limit headers to response if it is a Response object
            try:
                if hasattr(response, 'headers'):
                    response.headers['X-RateLimit-Limit'] = str(limit)
                    response.headers['X-RateLimit-Remaining'] = str(remaining)
                    response.headers['X-RateLimit-Reset'] = str(reset_epoch)
            except Exception:
                pass

            return response
        return wrapped
    return decorator
