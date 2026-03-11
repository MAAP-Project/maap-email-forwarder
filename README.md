## MAAP Email Forwarder

This project implements an email forwarding service using AWS CDK, Lambda, S3, and SES.

### Features
- **AWS CDK**: Infrastructure as code for easy deployment and management.
- **Lambda**: Serverless function to process and forward emails.
- **S3**: Storage for incoming emails.
- **SES**: Email receiving and sending service.

### Getting Started
To deploy this project, you will need to have the following tools installed:
- [AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html)
- [Node.js](https://nodejs.org/)
- [Python](https://www.python.org/)
- [uv](https://docs.astral.sh/uv/)

To deploy the project, you will need to have an SES verified domain connected to a Route53 hosted zone already set up. For more information on setting up an SES verified domain, see [Verify a New Domain in Amazon SES](https://docs.aws.amazon.com/ses/latest/dg/creating-identities.html). By default, account SES regions are in `sandbox` mode and must be moved to `production` to send emails to unverified addresses.

### Development
1. **Clone the repository**:
    ```bash
    git clone https://github.com/MAAP-Project/maap-email-forwarder.git
    cd maap-email-forwarder
    ```

2. **Install dependencies**:
    ```bash
    uv sync
    ```

3. **Run the tests**:
    ```bash
    uv run pytest -q
    ```

4. **Verify the stack**:
    ```bash
    uv run cdk synth
    ```

### Configuration
- `from_email`: The email address to use as the sender.
- `subject_prefix`: The prefix to add to the subject line of forwarded emails.
- `email_bucket`: The S3 bucket name for storing emails.
- `email_key_prefix`: The prefix for email objects in the S3 bucket.
- `forward_mapping`: A mapping of recipient emails to forward to.

To add a new email forward, update the `forward_mapping` repository variable in Github settings, following the existing convention and ensuring that it is a valid JSON object.

### License
This project is licensed under the Apache License. See the [LICENSE](LICENSE) file for details.
