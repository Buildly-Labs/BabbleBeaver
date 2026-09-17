"""
LLM Manager for multi-provider support with fallback capabilities.
Supports Gemini, OpenAI, DigitalOcean, and other hosted LLM providers.
"""

import os
import logging
import sys
import time
from typing import Optional, List, Dict, Callable, Any
from enum import Enum
import openai
import google.generativeai as genai

# Try to import Vertex AI (optional)
try:
    import vertexai
    from vertexai.generative_models import GenerativeModel
    VERTEXAI_AVAILABLE = True
except ImportError:
    VERTEXAI_AVAILABLE = False
    vertexai = None
    GenerativeModel = None

# Try to import DigitalOcean agent (optional)
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'modules'))
    from digitalocean import DigitalOceanAgent
    DIGITALOCEAN_AVAILABLE = True
except ImportError:
    DIGITALOCEAN_AVAILABLE = False
    DigitalOceanAgent = None

logger = logging.getLogger(__name__)


class AllProvidersFailedError(Exception):
    """
    Raised by LLMManager.generate() when every attempted provider failed.
    Carries `attempts` (list of (provider_name, provider_type, latency_ms,
    error_or_None) tuples) so callers can record which provider(s) were
    actually tried, not just guess based on configured order.
    """

    def __init__(self, message: str, attempts: List[tuple]):
        super().__init__(message)
        self.attempts = attempts


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    GEMINI = "gemini"
    OPENAI = "openai"
    HUGGINGFACE = "huggingface"
    DIGITALOCEAN = "digitalocean"
    CUSTOM = "custom"  # Bring-your-own-token: any OpenAI-compatible endpoint
    # (local runtimes like Ollama/vLLM/LM Studio, or a hosted OpenAI-compatible API)


class LLMConfig:
    """Configuration for an LLM provider."""

    def __init__(
        self,
        provider: LLMProvider,
        model_name: str,
        api_key: str,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        priority: int = 0,
        enabled: bool = True,
        name: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        self.provider = provider
        self.model_name = model_name
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.priority = priority  # Lower number = higher priority
        self.enabled = enabled
        # `name` distinguishes multiple configs of the same provider type (e.g.
        # several CUSTOM/BYOT endpoints). Defaults to the provider's own value.
        self.name = name or provider.value
        # Only used by CUSTOM (and any future provider needing a user-supplied endpoint).
        self.base_url = base_url

    def to_dict(self) -> Dict:
        """Convert config to dictionary (without exposing API key)."""
        return {
            "provider": self.provider,
            "name": self.name,
            "model_name": self.model_name,
            "base_url": self.base_url,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "priority": self.priority,
            "enabled": self.enabled,
            "api_key_configured": bool(self.api_key)
        }


class LLMManager:
    """
    Manages multiple LLM providers with automatic fallback.
    Attempts providers in priority order until one succeeds.
    """
    
    def __init__(self):
        self.providers: List[LLMConfig] = []
        self._initialize_from_env()
    
    def _initialize_from_env(self):
        """Initialize provider configurations from environment variables."""
        # Check if using Vertex AI (GCP) or standard Gemini API
        project_id = os.getenv("PROJECT_ID")
        location = os.getenv("LOCATION", "us-west1")
        
        # Gemini configuration
        gemini_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        
        # Use Vertex AI if PROJECT_ID is set and vertexai is available
        if project_id and VERTEXAI_AVAILABLE:
            logger.info(f"Initializing Vertex AI with project: {project_id}, location: {location}")
            vertexai.init(project=project_id, location=location)
            gemini_model = os.getenv("VERTEX_MODEL_NAME") or os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
            self.add_provider(LLMConfig(
                provider=LLMProvider.GEMINI,
                model_name=gemini_model,
                api_key=gemini_key or "vertex-ai",  # Vertex AI doesn't need API key
                priority=int(os.getenv("GEMINI_PRIORITY", "0")),
                enabled=os.getenv("GEMINI_ENABLED", "true").lower() == "true"
            ))
        elif gemini_key:
            logger.info("Initializing standard Gemini API")
            gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
            self.add_provider(LLMConfig(
                provider=LLMProvider.GEMINI,
                model_name=gemini_model,
                api_key=gemini_key,
                priority=int(os.getenv("GEMINI_PRIORITY", "0")),
                enabled=os.getenv("GEMINI_ENABLED", "true").lower() == "true"
            ))
            genai.configure(api_key=gemini_key)
        
        # OpenAI configuration
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            self.add_provider(LLMConfig(
                provider=LLMProvider.OPENAI,
                model_name=openai_model,
                api_key=openai_key,
                priority=int(os.getenv("OPENAI_PRIORITY", "1")),
                enabled=os.getenv("OPENAI_ENABLED", "true").lower() == "true"
            ))
            openai.api_key = openai_key
        
        # HuggingFace configuration (placeholder for future implementation)
        hf_key = os.getenv("HUGGINGFACE_AUTH_TOKEN")
        if hf_key:
            hf_model = os.getenv("HUGGINGFACE_MODEL", "meta-llama/Llama-2-7b-chat-hf")
            self.add_provider(LLMConfig(
                provider=LLMProvider.HUGGINGFACE,
                model_name=hf_model,
                api_key=hf_key,
                priority=int(os.getenv("HUGGINGFACE_PRIORITY", "2")),
                enabled=os.getenv("HUGGINGFACE_ENABLED", "false").lower() == "true"
            ))
        
        # DigitalOcean Gradient AI Platform configuration
        do_token = os.getenv("DIGITALOCEAN_API_TOKEN")
        do_url = os.getenv("DIGITALOCEAN_AGENT_URL")
        if do_token and do_url:
            self.add_provider(LLMConfig(
                provider=LLMProvider.DIGITALOCEAN,
                model_name=do_url,  # Store agent URL as model_name
                api_key=do_token,
                priority=int(os.getenv("DIGITALOCEAN_PRIORITY", "3")),
                enabled=os.getenv("DIGITALOCEAN_AGENT_ENABLED", "false").lower() == "true"
            ))

        # Bring-your-own-token (BYOT) custom endpoints: any OpenAI-compatible API
        # (local runtimes such as Ollama/vLLM/LM Studio, or a self-hosted/third-party
        # OpenAI-compatible service). Configure one or more via:
        #   CUSTOM_ENDPOINTS=mylocal,myvendor
        #   CUSTOM_MYLOCAL_BASE_URL=http://localhost:11434/v1
        #   CUSTOM_MYLOCAL_MODEL=llama3.1
        #   CUSTOM_MYLOCAL_API_KEY=ollama          (many local runtimes accept any string)
        #   CUSTOM_MYLOCAL_PRIORITY=0
        #   CUSTOM_MYLOCAL_ENABLED=true
        custom_endpoint_names = [
            n.strip() for n in os.getenv("CUSTOM_ENDPOINTS", "").split(",") if n.strip()
        ]
        for endpoint_name in custom_endpoint_names:
            prefix = f"CUSTOM_{endpoint_name.upper()}_"
            base_url = os.getenv(f"{prefix}BASE_URL")
            if not base_url:
                logger.warning(
                    f"CUSTOM endpoint '{endpoint_name}' listed in CUSTOM_ENDPOINTS but "
                    f"{prefix}BASE_URL is not set; skipping."
                )
                continue
            self.add_provider(LLMConfig(
                provider=LLMProvider.CUSTOM,
                name=endpoint_name,
                model_name=os.getenv(f"{prefix}MODEL", "default"),
                api_key=os.getenv(f"{prefix}API_KEY", "not-needed"),
                base_url=base_url,
                priority=int(os.getenv(f"{prefix}PRIORITY", "0")),
                enabled=os.getenv(f"{prefix}ENABLED", "true").lower() == "true"
            ))

        # Sort providers by priority
        self.providers.sort(key=lambda x: x.priority)
    
    def add_provider(self, config: LLMConfig):
        """Add a new provider configuration."""
        self.providers.append(config)
        self.providers.sort(key=lambda x: x.priority)
    
    def remove_provider(self, provider: LLMProvider):
        """Remove a provider by type."""
        self.providers = [p for p in self.providers if p.provider != provider]
    
    def get_provider_config(self, provider: LLMProvider) -> Optional[LLMConfig]:
        """Get configuration for a specific provider (first enabled match, by type)."""
        for config in self.providers:
            if config.provider == provider and config.enabled:
                return config
        return None

    def get_provider_config_by_name(self, name: str) -> Optional[LLMConfig]:
        """
        Get configuration by its unique name. Needed to distinguish multiple
        configs of the same provider type (e.g. several named CUSTOM/BYOT
        endpoints), where get_provider_config() would only ever return the first.
        """
        for config in self.providers:
            if config.name == name and config.enabled:
                return config
        return None
    
    def list_providers(self) -> List[Dict]:
        """List all configured providers."""
        return [p.to_dict() for p in self.providers]
    
    def _call_gemini(self, config: LLMConfig, prompt: str, **kwargs) -> str:
        """Call Gemini API (standard or Vertex AI)."""
        try:
            # Get system prompt if provided
            system_prompt = kwargs.get('system_prompt', '')
            full_prompt = f"{system_prompt}\n\nUser Question:\n{prompt}" if system_prompt else prompt
            
            # Check if using Vertex AI
            project_id = os.getenv("PROJECT_ID")
            
            if project_id and VERTEXAI_AVAILABLE:
                # Use Vertex AI
                model = GenerativeModel(config.model_name)
                response = model.generate_content(
                    full_prompt,
                    generation_config={
                        'max_output_tokens': kwargs.get('max_tokens', config.max_tokens),
                        'temperature': kwargs.get('temperature', config.temperature)
                    }
                )
                return response.text
            else:
                # Use standard Gemini API
                model = genai.GenerativeModel(config.model_name)
                response = model.generate_content(
                    full_prompt,
                    generation_config=genai.GenerationConfig(
                        max_output_tokens=kwargs.get('max_tokens', config.max_tokens),
                        temperature=kwargs.get('temperature', config.temperature)
                    )
                )
                return response.text
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise
    
    def _call_openai(self, config: LLMConfig, prompt: str, **kwargs) -> str:
        """Call OpenAI API."""
        try:
            system_prompt = kwargs.get('system_prompt', '')
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            client = openai.OpenAI(api_key=config.api_key)
            response = client.chat.completions.create(
                model=config.model_name,
                messages=messages,
                max_tokens=kwargs.get('max_tokens', config.max_tokens),
                temperature=kwargs.get('temperature', config.temperature)
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise
    
    def _call_huggingface(self, config: LLMConfig, prompt: str, **kwargs) -> str:
        """Call HuggingFace Inference API (placeholder)."""
        # TODO: Implement HuggingFace inference
        raise NotImplementedError("HuggingFace inference not yet implemented")

    def _call_custom(self, config: LLMConfig, prompt: str, **kwargs) -> str:
        """
        Call a bring-your-own-token (BYOT) endpoint: any OpenAI-compatible API,
        whether a local runtime (Ollama, vLLM, LM Studio) or a hosted third-party
        service the user points at via base_url.
        """
        try:
            system_prompt = kwargs.get('system_prompt', '')
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            client = openai.OpenAI(api_key=config.api_key, base_url=config.base_url)
            response = client.chat.completions.create(
                model=config.model_name,
                messages=messages,
                max_tokens=kwargs.get('max_tokens', config.max_tokens),
                temperature=kwargs.get('temperature', config.temperature)
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Custom endpoint '{config.name}' error: {e}")
            raise
    
    def _call_digitalocean(self, config: LLMConfig, prompt: str, **kwargs) -> str:
        """Call DigitalOcean Gradient AI Platform agent."""
        if not DIGITALOCEAN_AVAILABLE:
            raise Exception("DigitalOcean agent module not available")
        
        try:
            import asyncio
            import nest_asyncio
            
            # Allow nested event loops (needed when called from FastAPI async context)
            try:
                nest_asyncio.apply()
            except Exception:
                pass  # Already applied or not needed
            
            # Create agent with stored configuration
            agent = DigitalOceanAgent(
                api_token=config.api_key,
                agent_url=config.model_name,  # URL is stored in model_name
                timeout=kwargs.get('timeout', 90.0)
            )
            
            # Get context and system_prompt from kwargs if provided
            context = kwargs.get('context', None)
            system_prompt = kwargs.get('system_prompt', None)
            
            # Call agent (async) - handle both sync and async contexts
            try:
                # Try to get existing event loop
                loop = asyncio.get_running_loop()
                # If we're in an async context, create a task and run it
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        agent.chat_completion(prompt=prompt, context=context, system_prompt=system_prompt, stream=False)
                    )
                    response = future.result(timeout=kwargs.get('timeout', 90.0))
            except RuntimeError:
                # No running event loop, safe to use asyncio.run
                response = asyncio.run(agent.chat_completion(
                    prompt=prompt,
                    context=context,
                    system_prompt=system_prompt,
                    stream=False
                ))
            
            if not response:
                raise Exception("DigitalOcean agent returned no response")
            
            return response
            
        except Exception as e:
            logger.error(f"DigitalOcean agent error: {e}")
            raise
    
    def generate(
        self,
        prompt: str,
        preferred_provider: Optional[LLMProvider] = None,
        provider_order: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate text using available LLM providers with fallback.

        Args:
            prompt: The prompt to send to the LLM
            preferred_provider: Optional single provider type to try first
            provider_order: Optional list of provider *names* (see LLMConfig.name)
                specifying the exact try order, e.g. from task-based routing.
                Any enabled providers not listed are appended afterward, so
                task routing can prefer specific providers without losing the
                fallback safety net.
            **kwargs: Additional parameters (max_tokens, temperature, etc.)

        Returns:
            Dictionary with response text and metadata

        Raises:
            Exception: If all providers fail
        """
        providers_to_try = self.providers.copy()

        if provider_order:
            by_name = {p.name: p for p in providers_to_try}
            ordered = [by_name[name] for name in provider_order if name in by_name]
            remaining = [p for p in providers_to_try if p.name not in provider_order]
            providers_to_try = ordered + remaining

        # If preferred provider specified, try it first
        if preferred_provider:
            config = self.get_provider_config(preferred_provider)
            if config:
                providers_to_try = [config] + [p for p in providers_to_try if p.provider != preferred_provider]

        # Filter to only enabled providers
        providers_to_try = [p for p in providers_to_try if p.enabled]

        if not providers_to_try:
            raise Exception("No LLM providers configured or enabled")

        last_error = None
        attempts = []  # (provider_name, provider_type, latency_ms, error_or_None)

        for config in providers_to_try:
            attempt_start = time.monotonic()
            try:
                logger.info(f"Attempting to use {config.provider} ({config.model_name})")

                if config.provider == LLMProvider.GEMINI:
                    response_text = self._call_gemini(config, prompt, **kwargs)
                elif config.provider == LLMProvider.OPENAI:
                    response_text = self._call_openai(config, prompt, **kwargs)
                elif config.provider == LLMProvider.HUGGINGFACE:
                    response_text = self._call_huggingface(config, prompt, **kwargs)
                elif config.provider == LLMProvider.DIGITALOCEAN:
                    response_text = self._call_digitalocean(config, prompt, **kwargs)
                elif config.provider == LLMProvider.CUSTOM:
                    response_text = self._call_custom(config, prompt, **kwargs)
                else:
                    logger.warning(f"Unknown provider: {config.provider}")
                    continue

                latency_ms = int((time.monotonic() - attempt_start) * 1000)
                attempts.append((config.name, config.provider, latency_ms, None))

                return {
                    "response": response_text,
                    "provider": config.provider,
                    "provider_name": config.name,
                    "model": config.model_name,
                    "success": True,
                    "latency_ms": latency_ms,
                    "attempts": attempts
                }

            except Exception as e:
                latency_ms = int((time.monotonic() - attempt_start) * 1000)
                attempts.append((config.name, config.provider, latency_ms, str(e)))
                last_error = e
                logger.warning(f"Provider {config.provider} failed: {e}. Trying next provider...")
                continue

        # All providers failed
        error_msg = f"All LLM providers failed. Last error: {last_error}"
        logger.error(error_msg)
        raise AllProvidersFailedError(error_msg, attempts)
    
    def update_provider_config(
        self,
        provider: LLMProvider,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        priority: Optional[int] = None,
        enabled: Optional[bool] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ):
        """Update configuration for an existing provider."""
        config = self.get_provider_config(provider)
        
        if not config:
            # Find disabled config or create new one
            for c in self.providers:
                if c.provider == provider:
                    config = c
                    break
            
            if not config:
                raise ValueError(f"Provider {provider} not found")
        
        if model_name is not None:
            config.model_name = model_name
        if api_key is not None:
            config.api_key = api_key
        if priority is not None:
            config.priority = priority
        if enabled is not None:
            config.enabled = enabled
        if max_tokens is not None:
            config.max_tokens = max_tokens
        if temperature is not None:
            config.temperature = temperature
        
        # Re-sort by priority
        self.providers.sort(key=lambda x: x.priority)


# Global LLM manager instance
llm_manager = LLMManager()
