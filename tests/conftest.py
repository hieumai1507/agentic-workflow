"""
Pytest configuration and global fixtures.
"""
import pytest
import os

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["DOWNSTREAM_API_BASE_URL"] = "http://localhost:8001"
