# GitHub Action: Publish Flutter Package

If you don't have a publishing workflow, you can create one at `.github/workflows/publish.yml` with the following content:

```yaml
# .github/workflows/publish.yml
name: Publish to pub.dev

on:
  push:
    tags:
    # must align with the tag-pattern configured on pub.dev, often just replace
      # {{version}} with [0-9]+.[0-9]+.[0-9]+
    - 'v[0-9]+.[0-9]+.[0-9]+' # tag-pattern on pub.dev: 'v{{version}}'
    # If you prefer tags like '1.2.3', without the 'v' prefix, then use:
    # - '[0-9]+.[0-9]+.[0-9]+' # tag-pattern on pub.dev: '{{version}}'
    # If your repository contains multiple packages consider a pattern like:
    # - 'my_package_name-v[0-9]+.[0-9]+.[0-9]+'

# Publish using the reusable workflow from dart-lang.
jobs:
  publish:
    permissions:
      id-token: write # Required for authentication using OIDC
    uses: dart-lang/setup-dart/.github/workflows/publish.yml@v1
    # with:
    #   working-directory: path/to/package/within/repository
```

Note: This workflow uses OIDC for authentication, which is the recommended way to publish to pub.dev from GitHub Actions.
You will need to configure your package on pub.dev to allow publishing from your GitHub repository.

For more information, see:
- [Automated publishing](https://dart.dev/tools/pub/automated-publishing)
- [Publishing packages](https://dart.dev/tools/pub/publishing)
