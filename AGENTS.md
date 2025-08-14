# PoemAI GitHub Actions - AI Agent Guidelines

## Tagging Guidelines

### Before Creating New Tags

**ALWAYS** check existing tags before creating new versions:

```bash
git tag --list | sort -V
```

### Current Tag Strategy

- **Major versions** (v3.x.x): Breaking changes to action interfaces
- **Minor versions** (v3.1.x): New features, backward compatible
- **Patch versions** (v3.1.1): Bug fixes, backward compatible

### Version History

- **v3.1.0**: Latest stable version with hash-based build support
- **v3.0.0**: Major refactor with new action interfaces
- **v2.1.0**: Added manifest URL and build number support
- **v2.0.0**: Enhanced dependency triggering
- **v1.x.x**: Legacy versions

### Creating New Tags

1. Check existing tags: `git tag --list | sort -V`
2. Choose appropriate version number based on changes
3. Create annotated tag: `git tag -a vX.Y.Z -m "Description"`
4. Push tag: `git push origin vX.Y.Z`

### Action Usage

Users can reference specific versions:
- `uses: poemAI-ch/poemai-github-actions/action-name@v3.1.0` (specific version)
- `uses: poemAI-ch/poemai-github-actions/action-name@v3` (latest v3.x.x)
- `uses: poemAI-ch/poemai-github-actions/action-name@main` (latest development)

## AI Agent Notes

When modifying actions:
1. **Always check tags first** before creating new versions
2. **Update documentation** for any interface changes
3. **Test thoroughly** before tagging
4. **Use semantic versioning** appropriately
5. **Create release notes** for major changes

## Actions in this Repository

### trigger-dependents
- **Purpose**: Triggers downstream repository builds via Lambda
- **Latest Version**: v3.1.0 (as of last update)
- **Key Features**: Hash-based builds, environment-aware triggering

### deploy-cloudformation-stacks  
- **Purpose**: Deploys CloudFormation stacks with lambda support
- **Latest Version**: v3.1.0 (as of last update)
- **Key Features**: Lambda-based deployment, stack dependencies

### invoke-lambda
- **Purpose**: Invokes AWS Lambda functions from GitHub Actions
- **Latest Version**: v2.0.0 (as of last update)

### register-dependencies
- **Purpose**: Registers project dependencies in S3 for trigger system
- **Latest Version**: v2.0.0 (as of last update)
