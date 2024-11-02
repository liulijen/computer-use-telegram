# Using Anthropic Computer with Telegram on a Sandboxed Linux System

[Anthropic Computer Use](https://github.com/anthropics/anthropic-quickstarts/blob/main/computer-use-demo/README.md) is a beta feature from Anthropic that operates a Docker image with Ubuntu. This fork lets you control it via Telegram.

> [!CAUTION]
> Computer use is a beta feature. Please be aware that computer use poses unique risks that are distinct from standard API features or chat interfaces. These risks are heightened when using computer use to interact with the internet. To minimize risks, consider taking precautions such as:
>
> 1. Use a dedicated virtual machine or container with minimal privileges to prevent direct system attacks or accidents.
> 2. Avoid giving the model access to sensitive data, such as account login information, to prevent information theft.
> 3. Limit internet access to an allowlist of domains to reduce exposure to malicious content.
> 4. Ask a human to confirm decisions that may result in meaningful real-world consequences as well as any tasks requiring affirmative consent, such as accepting cookies, executing financial transactions, or agreeing to terms of service.
>
> In some circumstances, Claude will follow commands found in content even if it conflicts with the user's instructions. For example, instructions on webpages or contained in images may override user instructions or cause Claude to make mistakes. We suggest taking precautions to isolate Claude from sensitive data and actions to avoid risks related to prompt injection.
>
> Finally, please inform end users of relevant risks and obtain their consent prior to enabling computer use in your own products.

This repository helps you get started with computer use on Claude, with reference implementations of:

* Build files to create a Docker container with all necessary dependencies
* A computer use agent loop using the Anthropic API, Bedrock, or Vertex to access the updated Claude 3.5 Sonnet model
* Anthropic-defined computer use tools
* A Telegram bot for interacting with the agent loop


> [!IMPORTANT]
> The Beta API used in this reference implementation is subject to change. Please refer to the [API release notes](https://docs.anthropic.com/en/release-notes/api) for the most up-to-date information.

> [!IMPORTANT]
> The components are weakly separated: the agent loop runs in the container being controlled by Claude, can only be used by one session at a time, and must be restarted or reset between sessions if necessary.

## Quickstart: running the Docker container

## Development

```bash
./setup.sh  # configure venv, install development dependencies, and install pre-commit hooks
docker build . -t computer-use-demo:local  # manually build the docker image (optional)
export ANTHROPIC_API_KEY=%your_api_key%
export TELEGRAM_BOT_TOKEN=%your_telegram_bot_token%  # Get from @BotFather
export TELEGRAM_USER_ID=%your_telegram_user_id%  # Get your user ID from @userinfobot

docker run \
    -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
    -e TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN \
    -e TELEGRAM_USER_ID=$TELEGRAM_USER_ID \
    -v $(pwd)/computer_use_demo:/home/computeruse/computer_use_demo/ `# mount local python module for development` \
    -v $HOME/.anthropic:/home/computeruse/.anthropic \
    -p 5900:5900 \
    -p 8501:8501 \
    -p 6080:6080 \
    -p 8080:8080 \
    -it computer-use-demo:local
```

The docker run command above mounts the repo inside the docker image, such that you can edit files from the host. Streamlit is already configured with auto reloading.

### Environment Variables

- `ANTHROPIC_API_KEY`: Your Anthropic API key
- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token from @BotFather
- `TELEGRAM_USER_ID`: Your Telegram user ID (required for bot access control)
- `API_PROVIDER`: Optional, defaults to "anthropic"
- `WIDTH` and `HEIGHT`: Optional screen dimensions

### Telegram Usage

Once you have configured your Telegram bot token and user ID, you can interact with Claude through Telegram:

1. Start a chat with your bot
2. Type messages to interact with Claude
3. Use `/stop` command to force stop the current session

The bot will only respond to messages from the configured user ID for security.
