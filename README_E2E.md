# End-to-End (E2E) Testing Guide

This document describes how to run and maintain the End-to-End tests for the Private Drive application.

## Prerequisites

- **Python 3.12+**
- **Playwright Browsers:** The E2E tests use Playwright. If browsers are not installed, run:
  ```bash
  ./venv/bin/playwright install
  ```
- **Virtual Environment:** Ensure the `./venv` directory is set up with all dependencies from `requirements.txt`.

## Running Tests

### Using the Helper Script (Recommended)
A helper script `run_e2e.sh` is provided to simplify the process. It automatically handles `PYTHONPATH` and virtual environment activation.

```bash
./run_e2e.sh
```

To run in headless mode (no browser window):
```bash
./run_e2e.sh --headless
./run_e2e.sh --headed --slowmo 2000 -s
```

### Manual Execution
If you prefer to run tests manually, ensure your `PYTHONPATH` includes the project root:

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
source venv/bin/activate
pytest tests/e2e/ --headed -s
```

## Recent Improvements to `run_e2e.sh`

The `run_e2e.sh` script was recently updated to address several issues:
1. **Directory-wide Testing:** Previously, it only ran a single test file. It now executes all tests in `tests/e2e/`.
2. **Automatic Venv Activation:** The script now checks for and activates the local `venv` automatically.
3. **Robust Paths:** Uses absolute paths for `PYTHONPATH` to prevent import errors regardless of where the script is invoked.
4. **Error Handling:** Added `set -e` to stop execution immediately if a test session fails to start or encounters a critical error.

## Troubleshooting

- **"Executable doesn't exist"**: This usually means Playwright browsers aren't installed in the expected location. Run `playwright install`.
- **Import Errors**: Ensure you are running the script from the project root so that the `app` module can be discovered via `PYTHONPATH`.
