# AWS CLI Local Setup

Use this guide when the user needs to upload a Flutter Web build from a local machine with `scripts/release_web_s3.py`.

## 1. Install AWS CLI

```bash
brew install awscli
```

Verify the installation:

```bash
aws --version
```

## 2. Get Access Key And Secret Key

Ask the user to obtain the access key ID (`ak`) and secret access key (`sk`) from the OSS or S3-compatible storage provider.

Do not ask the user to commit these values into `deploy/s3.env.example` or any tracked file.

## 3. Create A Named AWS CLI Profile

Configure a dedicated profile instead of relying on the default profile:

```bash
aws configure --profile <new-profile-name>
```

Then enter the provider values interactively:

1. `AWS Access Key ID`: enter the provider `ak`
2. `AWS Secret Access Key`: enter the provider `sk`
3. `Default region name`: enter the provider region, usually `auto` or the provider's assigned region code (e.g. `cn-east-1` for Bitiful). **Do not leave it blank or enter garbage** — if the region is invalid, the AWS CLI signs requests incorrectly and the provider returns `SignatureDoesNotMatch` even with correct credentials.
4. `Default output format`: optional, `json` is fine

**Verify the profile works before uploading**:

```bash
aws --profile <profile-name> --endpoint-url <endpoint> s3 ls s3://<bucket>/
```

If you see `SignatureDoesNotMatch`, the most common cause is a corrupted `region` in `~/.aws/config` for that profile. Fix it:

```bash
aws configure --profile <profile-name> set region <correct-region>
```

This writes local credentials into the AWS CLI config files under the user's home directory.

## 4. Use The Profile In Release Commands

`release_web_s3.py` already supports `AWS_PROFILE`. Set it before running the release:

```bash
export AWS_PROFILE=<profile-name>
```

Or put it in `deploy/s3.env`:

```dotenv
AWS_PROFILE=<profile-name>
```

Internally, the script passes `--profile <profile-name>` to `aws`, so the configured profile is used consistently for S3 list, sync, copy, and promote operations.

Do not recommend local uploads that depend only on `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. Some S3-compatible providers fail in that mode and only work when the AWS CLI reads credentials from a named `AWS_PROFILE`.

## 5. Optional Project Example

If the project uses `deploy/s3.env`, keep the profile name there and keep the file untracked:

```dotenv
AWS_PROFILE=my-oss-profile
S3_ENDPOINT_URL=https://s3.example.com
S3_BUCKET=my-bucket
S3_REGION=auto
```

Do not store raw `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` in tracked project files. For local uploads, prefer `AWS_PROFILE` even if the provider also documents direct environment variables.
