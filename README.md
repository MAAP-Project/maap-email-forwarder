# MAAP Email Forwarder

This project implements an email forwarding service using AWS CDK, Lambda, S3, and SES.

## Features

- **AWS CDK**: Infrastructure as code for easy deployment and management.
- **Lambda**: Serverless function to process and forward emails.
- **S3**: Storage for incoming emails.
- **SES**: Email receiving and sending service.

## Getting Started

To deploy this project, you will need to have the following tools installed:

- [AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html)
- [Node.js](https://nodejs.org/)
- [Python](https://www.python.org/)
- [uv](https://docs.astral.sh/uv/)

To deploy the project, you will need to have an SES verified domain connected to a Route53 hosted zone already set up. For more information on setting up an SES verified domain, see [Verify a New Domain in Amazon SES](https://docs.aws.amazon.com/ses/latest/dg/creating-identities.html). By default, account SES regions are in `sandbox` mode and must be moved to `production` to send emails to unverified addresses.

## Contributing

### 1. Prerequisites

First, ensure you have [uv](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer) installed. You can install it using one of the official commands:

- **pip:** Suggested: `pipx install uv` or `pip install uv`
- **Homebrew:** `brew install uv`
- **macOS/Linux:** `curl -LsSf https://astral.sh | sh`
- **Windows:** `powershell -c "irm https://astral.sh | iex"`

### 2. Development Setup

1. **Fork and clone** the repository.
2. **Install project dependencies** (this automatically sets up a virtual environment):

   ```bash
   uv sync
   ```

3. **Install the pre-commit hooks** so your code is automatically linted before every commit:

   ```bash
   uv run pre-commit install
   ```

### 3. Verification Commands

- **Manually run lints across all files:**

  ```bash
  uv run pre-commit run --all-files
  ```

- **Run the tests:**

    ```bash
    uv run pytest -q
    ```

## Configuration

- `from_email`: The email address to use as the sender.
- `subject_prefix`: The prefix to add to the subject line of forwarded emails.
- `email_bucket`: The S3 bucket name for storing emails.
- `email_key_prefix`: The prefix for email objects in the S3 bucket.
- `forward_mapping`: A mapping of recipient emails to forward to.

To add a new email forward, update the `forward_mapping` repository variable in Github settings, following the existing convention and ensuring that it is a valid JSON object.

## License

This project is licensed under the Apache License. See the [LICENSE](LICENSE) file for details.
