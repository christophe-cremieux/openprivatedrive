# Contributing to OpenPrivateDrive

Thank you for considering contributing to Open Private Drive! 🎉

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md) (if present) and treat all contributors with respect.

## How Can I Contribute?

### Reporting Bugs

1. Check if the bug is already reported in [Issues](https://github.com/christophe-cremieux/openprivatedrive/issues)
2. Create a new issue with a clear title and description
3. Include:
   - Steps to reproduce
   - Expected behavior
   - Actual behavior
   - Screenshots (if applicable)
   - Environment (Docker / bare metal, browser version, etc.)

### Suggesting Features

We welcome feature requests! Please open an issue with:
- A clear description of the feature
- Why it would be useful
- Any implementation ideas

### Submitting Pull Requests

1. Fork the repository
2. Create a new branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Ensure tests pass (`pytest`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Development Setup

See the [README.md](README.md) for local development instructions.

Key points:
- Use the existing app factory pattern
- Add new business logic in `app/services/`
- All file/folder operations must go through the permission engine
- Follow PEP 8 style guidelines

## Pull Request Guidelines

- Keep PRs focused on a single feature or fix
- Update documentation if needed
- Add or update tests for new functionality
- Ensure the code works with both SQLite and Docker setups

## Development Priorities (in order)

1. Bug fixes & stability
2. Security improvements
3. Core features (encryption, sharing, permissions)
4. Usability & documentation
5. Nice-to-have features (versioning, WebDAV, etc.)

## Questions?

Feel free to open a [Discussion](https://github.com/christophe-cremieux/openprivatedrive/discussions) or contact the maintainer.

---

**Thank you for contributing to a more private internet!** 🔒
