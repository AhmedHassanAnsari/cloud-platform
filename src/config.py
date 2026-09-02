"""Configuration for AI agents using Gemini and OpenAI Agents SDK."""

import os
from dotenv import load_dotenv

load_dotenv()

# Gemini configuration (via google-generativeai)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Model configuration
GEMINI_MODEL = "gemini-2.5-flash-lite"  # Latest stable Gemini model

# Build & Deployment configuration
PROJECT_NAME = os.getenv("PROJECT_NAME", "cloud-platform")
GHCR_REGISTRY = os.getenv("GHCR_REGISTRY", "ghcr.io")

# Base images for frameworks
DEFAULT_BASE_IMAGE_PYTHON = os.getenv("DEFAULT_BASE_IMAGE_PYTHON", "python:3.12-alpine")
DEFAULT_BASE_IMAGE_NODEJS = os.getenv("DEFAULT_BASE_IMAGE_NODEJS", "node:20-alpine")
DEFAULT_BASE_IMAGE_RUST = os.getenv("DEFAULT_BASE_IMAGE_RUST", "rust:latest")
DEFAULT_BASE_IMAGE_GO = os.getenv("DEFAULT_BASE_IMAGE_GO", "golang:1.21-alpine")

# Base image mapping
BASE_IMAGES = {
    "python": DEFAULT_BASE_IMAGE_PYTHON,
    "nodejs": DEFAULT_BASE_IMAGE_NODEJS,
    "rust": DEFAULT_BASE_IMAGE_RUST,
    "go": DEFAULT_BASE_IMAGE_GO,
}

# Validation
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set in .env file")

