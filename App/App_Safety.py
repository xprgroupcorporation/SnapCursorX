"""
Crash protection and error handling utilities.
Prevents uncaught exceptions from crashing the app.
"""

import functools
import traceback
from typing import Callable, Any, TypeVar

F = TypeVar('F', bound=Callable[..., Any])


def safe_slot(func: F) -> F:
    """
    Decorator to make Qt signal/slot handlers crash-safe.
    Catches exceptions and logs them without crashing the app.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"[SLOT ERROR] {func.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            return None
    return wrapper


def safe_thread_worker(func: F) -> F:
    """
    Decorator for thread worker functions.
    Catches unhandled exceptions in background threads.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"[THREAD ERROR] {func.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            return None
    return wrapper


def safe_event_handler(func: F) -> F:
    """
    Decorator for event handlers (mouse, keyboard, etc).
    Prevents event handler crashes from propagating.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"[EVENT ERROR] {func.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            return False  # Return False for event handlers to indicate not handled
    return wrapper


def safe_call(func: Callable, *args, **kwargs) -> Any:
    """
    Safely call a function with error handling.
    Returns None if exception occurs.
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        print(f"[SAFE CALL ERROR] {func.__name__}: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None


def safe_cleanup(func: Callable) -> Callable:
    """
    Decorator for cleanup functions that should always run.
    Prevents cleanup errors from crashing the app.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"[CLEANUP ERROR] {func.__name__}: {type(e).__name__}: {e}")
            # Don't re-raise cleanup errors
            return None
    return wrapper


class SafeSignalEmitter:
    """Context manager for safely emitting Qt signals."""
    
    def __init__(self, signal, *args):
        self.signal = signal
        self.args = args
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                self.signal.emit(*self.args)
        except Exception as e:
            print(f"[SIGNAL EMIT ERROR]: {type(e).__name__}: {e}")
            traceback.print_exc()
        return False  # Don't suppress original exception


def wrap_qt_method(widget_class, method_name: str):
    """
    Wrap a Qt widget method to make it crash-safe.
    Used to patch methods after class definition.
    """
    original_method = getattr(widget_class, method_name)
    
    @functools.wraps(original_method)
    def safe_method(self, *args, **kwargs):
        try:
            return original_method(self, *args, **kwargs)
        except Exception as e:
            print(f"[QT METHOD ERROR] {widget_class.__name__}.{method_name}: {type(e).__name__}: {e}")
            traceback.print_exc()
            return None
    
    setattr(widget_class, method_name, safe_method)
