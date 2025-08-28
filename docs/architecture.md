# Library App Architecture

## Overview
This document provides an overview of the reorganized project architecture following industry-standard directory structure.

## Directory Structure

### `/src` - Core Application
Contains the main application logic:
- **api.py**: FastAPI application with REST endpoints
- **library.py**: Core library management business logic
- **main.py**: CLI interface built with Typer
- **book.py**: Book data model
- **database.py**: Database layer with SQLite integration

### `/src/services` - External Service Integrations
Houses all external service integrations:
- **google_books_service.py**: Google Books API integration
- **hugging_face_service.py**: AI features via Hugging Face
- **cache_manager.py**: Redis caching implementation
- **http_client.py**: Shared HTTP client abstraction

### `/config` - Configuration Management
Centralized configuration:
- **config.py**: Application configuration
- **.env.example**: Environment variables template
- **pytest.ini**: Test configuration
- **pyrightconfig.json**: Type checking configuration

### `/utils` - Utility Functions
Helper modules and utilities:
- **validators.py**: Input validation logic
- **ui_helpers.py**: CLI UI enhancement helpers
- **cli_config.py**: CLI-specific configuration

### `/scripts` - Automation Scripts
Utility scripts for maintenance and debugging:
- **debug_enhanced.py**: Debugging tools
- **enrich_existing_books.py**: Bulk data enrichment
- **quick_test.py**: Quick testing utilities

### `/static` - Web Interface
Frontend assets:
- **index.html**: Main web page
- **script.js**: JavaScript functionality
- **styles.css**: Styling
- **theme.js**: Theme management
- **background.js**: Background effects

### `/tests` - Test Suite
Comprehensive test coverage:
- Unit tests for individual modules
- Integration tests for API endpoints
- End-to-end testing scenarios

## Benefits of This Structure

1. **Modularity**: Clear separation of concerns
2. **Maintainability**: Related code is grouped together
3. **Scalability**: Easy to add new features and services
4. **Developer Experience**: Industry-standard organization
5. **Testing**: Isolated test structure
6. **Deployment**: Clean containerization support

## Import Structure

With the new organization, imports follow a hierarchical pattern:
- Core modules: `from src.module import Class`
- Services: `from src.services.service_name import Service`
- Utils: `from utils.util_name import function`
- Config: `from config.config import settings`

This structure makes dependencies explicit and improves code navigation.