# BabbleBeaver

BabbleBeaver is an open-source, provider-agnostic runtime for portable AI services and agents. It lets developers run AI workloads locally, in private infrastructure, or through providers of their choice, without coupling their application to one AI vendor.

## Overview

BabbleBeaver aims to democratize conversational AI, offering a plug-and-play solution that respects user privacy and data sovereignty. Built on top of FastAPI, BabbleBeaver facilitates rapid development and deployment of AI-powered chatbots and agents, routing requests through a swappable provider layer (`llm_manager.py`) instead of binding directly to any single vendor's SDK or API.

Portability is the point: the same application code should keep working whether requests are served by a local/self-hosted model, a private deployment, or a hosted provider — and switching between them should be a configuration change, not a rewrite.

## Installation

### Creating a .env file

To configure environment variables for BabbleBeaver, you need to create a `.env` file from the provided `example.env` file. Follow these steps:

1. Navigate to the project root directory where `example.env` is located.
2. Copy the `example.env` file to create a new `.env` file:
    ```bash
    cp example.env .env
    ```
3. Open the `.env` file in a text editor and update the values as needed. This file contains environment-specific variables such as API keys and configuration settings.

Make sure to keep the `.env` file secure and do not expose it publicly, as it may contain sensitive information.

For Gemini/Vertex AI, `GOOGLE_APPLICATION_CREDENTIALS` should point at a service account JSON key that you provision yourself in Google Cloud Console (IAM & Admin > Service Accounts) and store securely — never fetch credentials from a public URL or commit them to version control. See [SECURITY.md](SECURITY.md) for secrets-handling guidance.

To obtain the ENDPOINT_ID, the endpoint is found under the fine-tuned model in Model Garden

### Running the FastAPI application locally

- Make sure you have Python installed on your machine. You can download and install Python from the official website: https://www.python.org/downloads/

- Create a new directory for your project, then execute the following commands: `git clone https://github.com/YourUsername/BabbleBeaver.git
` followed by `cd BabbleBeaver` to navigate to the project root directory.

- Then execute the following commands which creates a virtual environment, activates it, then installs the necessary dependencies, followed by starting the application locally.

### VirtualENV
```bash
BabbleBeaver % virtualenv venv
BabbleBeaver % source venv/bin/activate
(venv) BabbleBeaver % pip install -r requirements.txt
(venv) BabbleBeave % uvicorn main:app --reload
```

- Make sure that if you're choosing to run the application using any of the following two methods, you have created and activated the virtual environment and have also installed all the necessary dependencies.

### Running the FastAPI application using Docker

To build the Docker image, then activate the docker environment and subsequently start the FastAPI server, run the following:
```
docker build -t babble-beaver .
docker run -p 8000:8000 babble-beaver
```

### Running the FastAPI application using Docker-Compose
```bash
docker-compose up --build
```

- **Ensure Docker and Docker Compose are installed on your system before running these commands.**

## Provider configuration

BabbleBeaver currently ships with built-in support for **Gemini/Vertex AI**, **OpenAI**, and **DigitalOcean Gradient AI agents**, managed centrally by `llm_manager.py`. Each provider is configured entirely through environment variables — no code changes needed to enable, disable, reprioritize, or reconfigure a provider that's already supported:

- `<PROVIDER>_ENABLED` — `true`/`false`
- `<PROVIDER>_PRIORITY` — lower number = tried first; `llm_manager` falls back to the next enabled provider on failure
- `<PROVIDER>_MODEL` / provider-specific keys (API keys, URLs, etc.)

See `example.env` for the full list of supported variables per provider.

**Adding support for a new provider** (one not already built in) currently requires implementing a `_call_<provider>` method in `llm_manager.py` and registering it in the `LLMProvider` enum and dispatch logic — there is no plugin/config-only mechanism yet. This is a known gap relative to BabbleBeaver's provider-agnostic goals; see [SECURITY.md](SECURITY.md) and open issues for the extension-point work in progress. `HuggingFace` is present in configuration but not yet implemented (`NotImplementedError`).

A `model_config/model_config.ini` file exists in the repo from an earlier architecture but is **not read by the running application** — ignore it; provider configuration is env-var driven as described above.

## Features

### Database Management
- **SQLite (Development)**: Zero-configuration database for local development
- **PostgreSQL (Production)**: Managed PostgreSQL support for DigitalOcean and Google Cloud Platform
- **Auto-Switching**: Automatically uses SQLite or PostgreSQL based on `DATABASE_URL` environment variable
- **ORM-Based**: SQLAlchemy models for messages and API tokens with connection pooling

See [DATABASE.md](devdocs/DATABASE.md) for complete setup instructions.

### DigitalOcean Gradient AI Integration
- **Agent Support**: Full integration with DigitalOcean Gradient AI Platform
- **Cost Estimation**: Real-time cost comparison across all providers (DigitalOcean, Gemini, OpenAI, Anthropic)
- **Multi-Provider**: Seamlessly switch between AI providers with fallback support

See [DIGITALOCEAN_AGENT.md](devdocs/DIGITALOCEAN_AGENT.md) for configuration details.

## Usage

After installation, BabbleBeaver can be accessed at `http://localhost:8000` by default. The API documentation, generated by FastAPI, is available at `http://localhost:8000/docs`.

## Architecture

BabbleBeaver adopts a modular architecture, with each conversational AI model implemented as a separate submodule. This allows for the easy addition, removal, or replacement of LLM implementations without affecting the core system.

- **Core System**: Built on FastAPI, the core handles API requests, routing, and integration with LLM submodules.
- **LLM Submodules**: Each LLM implementation is encapsulated within its Docker container, ensuring data isolation and security. Submodules communicate with the core system via RESTful APIs or message queues.
- **Data Layer**: For storing conversational logs, user data, and other relevant information, with support for encryption and GDPR compliance.

## Contributing

We welcome contributions! Please see our [Contributing Guidelines](/docs/CONTRIBUTING.md) for how to get involved. For setting up your development environment and the pull request process, refer to the guidelines.

## Community Guidelines

BabbleBeaver is committed to fostering an inclusive and safe community. Please read our [Community Guidelines](/docs/COMMUNITY_GUIDELINES.md) to understand our values and expectations.

# Product Vision Statement:
Our open-source project aims to create an accessible and robust conversational AI flexible software development platform. 

1. Select a Pre-trained Model
Choose a pre-trained model from Hugging Face's Transformers library that suits your needs for a conversational chatbot. Models like GPT (including GPT-2, GPT-3 if you have access through OpenAI's API, or GPT-Neo/GPT-J for fully open-source alternatives) are good starting points for building conversational agents.

2. Local Inference
Perform all inferences locally (or on your private cloud) to keep the data isolated. This means running the model on your own hardware without sending data out to third-party AI providers. Hugging Face Transformers library allows you to easily download pre-trained models and use them locally.

3. Fine-tuning (Optional)
If the pre-trained model doesn't meet your specific needs or you want to adapt it to your domain-specific conversations, you can fine-tune the model on your dataset. This step requires:

A custom dataset: Prepare a dataset representative of the conversations your chatbot will handle.
Compute resources: Fine-tuning LLMs can be resource-intensive, depending on the model size and dataset.
Keeping data isolated: Ensure your training process is conducted in a secure environment to maintain data privacy.


## License

BabbleBeaver is GPL-licensed. See the [LICENSE](LICENSE) file for details.

## Acknowledgments

This project was inspired by the open-source community and the need for privacy-respecting AI tools.

## Contact

For questions, suggestions, or contributions, please open an issue in this repository or contact us at [team@open.build](mailto:team@open.build).


## Why GPL for BabbleBeaver?
Copyleft: The GPL is a strong copyleft license, which means that any modified versions of the project must also be distributed under the GPL. This ensures that the main codebase and any derivatives remain open source, promoting collaboration and improvement.
Compatibility with Other Licenses for Sub-Repositories: While the GPL itself is strict about the licensing of derived works, it allows for linking or interfacing with software under different licenses under certain conditions.
