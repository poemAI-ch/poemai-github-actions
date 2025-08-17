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
- **Key Features**: Lambda-based deployment, stack dependencies, enhanced stack filtering

#### Recent Enhancements (August 2025)

**Enhanced Stack Filtering and Validation System**

The `deploy_with_lambda_call.py` script now includes comprehensive stack filtering improvements:

**Key Features Added:**

1. **Stack Name Validation**: Pre-validates stack names before processing
   - Comprehensive error messages listing all available stacks
   - Shows both base names and full names with environment suffixes
   - Helpful usage hints for developers

2. **Flexible Stack Name Support**: Both formats now work seamlessly
   - Base names: `poemai-github-role`
   - Full names: `poemai-github-role-development`

3. **Improved Error Handling**: 
   ```bash
   # Example error output with helpful suggestions
   ❌ Stack name 'non-existent-stack' does not match any available stacks.
   Available stack names (without environment suffix):
     - poemai-monitoring-sns-topic
     - poemai-lambda-crawler
   Available full stack names:
     - poemai-monitoring-sns-topic-staging
     - poemai-lambda-crawler-staging
   Note: You can use either the full name or just the base name.
   ```

4. **pytest Test Framework**: Comprehensive test suite for stack filtering
   - `test_stack_filtering_single_stack`: Tests specific stack filtering
   - `test_stack_filtering_all_stacks`: Tests processing all stacks
   - `test_stack_filtering_nonexistent_stack`: Tests error handling
   - `test_stack_filtering_both_name_formats`: Tests both name formats
   - `test_compare_stack_names`: Tests core name comparison logic

**Bug Fixes:**
- Fixed double environment suffix issue (e.g., `stack-two-development-development`)
- Improved config object handling to prevent mutations between test calls
- Enhanced debug logging for troubleshooting filtering issues

**Development Workflow Improvements:**
- Created `validate_cf_stacks.sh` convenience script with command-line options
- Modified `precommit.sh` to use local version during development
- Efficient focused testing instead of repeated CLI runs
- Support for environment-specific validation (`-e staging`)
- Support for single-stack validation (`-s stack-name`)
- Verbose mode for detailed debugging (`-v`)

**Usage Examples:**
```bash
# Test specific stack with verbose output
./validate_cf_stacks.sh -e staging -s poemai-monitoring-sns-topic -v

# Test all stacks in staging
./validate_cf_stacks.sh -e staging  

# Run comprehensive pytest tests
python -m pytest tests/test_deploy_with_lambda.py::test_stack_filtering_* -v
```

**Files Modified:**
- `deploy_with_lambda_call.py`: Added `validate_stack_name_filter()` function
- `tests/test_deploy_with_lambda.py`: Added 5 new test functions
- Enhanced error messages and stack name matching logic

### invoke-lambda
- **Purpose**: Invokes AWS Lambda functions from GitHub Actions
- **Latest Version**: v2.0.0 (as of last update)

### register-dependencies
- **Purpose**: Registers project dependencies in S3 for trigger system
- **Latest Version**: v2.0.0 (as of last update)
