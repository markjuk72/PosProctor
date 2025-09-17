# Contributing to GrafanaCommander

Thank you for your interest in contributing to the Verifone Commander Monitoring Stack! This guide will help you get started.

## 🚀 Getting Started

### Prerequisites
- Docker and Docker Compose
- Git
- Basic understanding of Python, Prometheus, and Grafana

### Setup for Development
1. Fork and clone the repository
2. Copy configuration templates:
   ```bash
   cp .env.example .env
   cp credentials.yaml.example credentials.yaml
   cp commanders.csv.example commanders.csv
   ```
3. Update configuration files with your test environment details
4. Start the development stack:
   ```bash
   docker-compose up -d
   ```

## 📝 Development Guidelines

### Code Style
- Follow existing Python conventions in the codebase
- Use meaningful variable and function names
- Add docstrings for complex functions
- Keep functions focused and single-purpose

### Testing
- Test changes with representative Commander loads
- Verify dashboards work correctly after modifications
- Ensure all services start properly with `docker-compose up`

### Configuration Changes
- Always provide example files for new configuration options
- Update documentation when adding new features
- Ensure backward compatibility when possible

## 🔧 Areas for Contribution

### High Priority
- **Additional POS System Support**: Extend beyond Verifone to other POS manufacturers
- **Enhanced Alerting**: More granular alert conditions and notification channels
- **Performance Optimization**: Improve query efficiency and resource usage
- **Documentation**: API documentation, deployment guides, troubleshooting

### Medium Priority
- **Dashboard Enhancements**: New visualizations and metrics
- **Security Improvements**: Authentication, encryption, secure defaults
- **Monitoring Extensions**: Additional device types and metrics
- **Integration**: Webhook notifications, external ticketing systems

### Low Priority
- **UI Improvements**: Better mobile responsiveness in Grafana dashboards
- **Analytics**: Historical trending, capacity planning features
- **Automation**: Auto-discovery of new devices

## 📊 Submitting Changes

### Pull Request Process
1. Create a feature branch from `master`
2. Make your changes with clear, descriptive commits
3. Test thoroughly in your development environment
4. Update documentation as needed
5. Submit a pull request with:
   - Clear description of changes
   - Testing steps performed
   - Screenshots for UI changes

### Commit Message Format
```
feat: Add support for new device type
fix: Resolve memory leak in polling loop
docs: Update deployment guide
refactor: Improve error handling
```

## 🐛 Reporting Issues

### Bug Reports
Include:
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Docker version)
- Log snippets (sanitized of sensitive data)

### Feature Requests
Include:
- Use case description
- Proposed implementation approach
- Potential impact on existing functionality

## 🔒 Security Considerations

- Never commit sensitive data (IPs, credentials, emails)
- Use example files for configuration templates
- Sanitize log outputs in issues and PRs
- Report security vulnerabilities privately

## 📞 Getting Help

- Check existing issues and documentation first
- Create detailed issue descriptions
- Join discussions on existing issues
- Consider contributing documentation improvements

## 🤝 Community

This project aims to be welcoming to contributors of all skill levels. We encourage:
- Constructive feedback and code reviews
- Knowledge sharing and documentation improvements
- Respectful communication and collaboration
- Learning opportunities for new contributors

Thank you for helping make this monitoring stack better for everyone!