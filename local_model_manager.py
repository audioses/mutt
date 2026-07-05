# local_model_manager.py - Improved version with better download handling

import os
import re
import json
import threading
import time
import subprocess
import requests
import signal
import warnings
from typing import Dict, List, Optional

# Global variables for lazy loading
_wx = None
_hf_api = None
_hf_hub_download = None
_inspect = None

def _import_hf_hub_and_wx():
    """Lazily import wx and huggingface_hub components."""
    global _wx, _hf_api, _hf_hub_download, _inspect
    if _wx is None:
        try:
            import wx as wx_local
            _wx = wx_local
        except ImportError:
            _wx = None # Mark as failed to import

    if _hf_api is None:
        try:
            from huggingface_hub import HfApi, hf_hub_download
            import inspect
            _hf_api = HfApi()
            _hf_hub_download = hf_hub_download
            _inspect = inspect
        except ImportError:
            _hf_api = None # Mark as failed to import
            _hf_hub_download = None
            _inspect = None

class LlamaServerManager:
    """Manages the llama-server.exe process and provides HTTP API interface"""

    def __init__(self, binary_path: str = None, port: int = 8080):
        self.binary_path = binary_path or os.path.join(os.getcwd(), "bin", "llama", "llama-server.exe")
        self.port = port
        self.base_url = f"http://localhost:{port}"
        self.process = None
        self.model_path = None
        self.is_running = False
        # Create logs directory if it doesn't exist
        self.logs_dir = os.path.join(os.getcwd(), "logs")
        os.makedirs(self.logs_dir, exist_ok=True)
        # Clean up old log files (keep only last 10)
        self._cleanup_old_logs()

    def is_server_running(self) -> bool:
        """Check if the llama-server is running and responding"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    def start_server(self, model_path: str, context_size: int = 32000, gpu_layers: int = -1) -> bool:
        """Start the llama-server with the specified model"""
        if self.is_server_running():
            print("Server is already running")
            return True

        if not os.path.exists(self.binary_path):
            raise FileNotFoundError(f"llama-server.exe not found at: {self.binary_path}")

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found at: {model_path}")

        self.model_path = model_path

        # Prepare command arguments
        cmd = [
            self.binary_path,
            "--model", model_path,
            "--ctx-size", str(context_size),
            "--port", str(self.port),
            "--host", "127.0.0.1",
            "--threads", "0",  # Auto-detect threads
            "--n-gpu-layers", str(gpu_layers),  # Enable GPU layers (-1 = all layers)
            "--verbose"
        ]

        # Create log file for this server instance
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        model_name = os.path.basename(model_path)
        if model_name.endswith('.gguf'):
            model_name = model_name[:-5]  # Remove .gguf extension
        log_file_path = os.path.join(self.logs_dir, f"llama_server_{model_name}_{timestamp}.log")

        try:
            print(f"Starting llama-server with command: {' '.join(cmd)}")
            print(f"Server log will be written to: {log_file_path}")
            
            # Open log file for writing
            self.log_file = open(log_file_path, 'w', encoding='utf-8')
            
            self.process = subprocess.Popen(
                cmd,
                stdout=self.log_file,
                stderr=self.log_file,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                text=True,
                bufsize=1  # Line buffered
            )

            # Wait for server to start
            for i in range(30):  # Wait up to 30 seconds
                if self.is_server_running():
                    self.is_running = True
                    print(f"llama-server started successfully on port {self.port}")
                    return True
                time.sleep(1)

            # If we get here, server failed to start
            self.stop_server()
            return False

        except Exception as e:
            print(f"Failed to start llama-server: {e}")
            # Close log file if it was opened
            if hasattr(self, 'log_file') and self.log_file:
                self.log_file.close()
                self.log_file = None
            return False

    def stop_server(self):
        """Stop the llama-server process"""
        if self.process:
            try:
                if os.name == 'nt':
                    self.process.terminate()
                else:
                    self.process.send_signal(signal.SIGTERM)

                # Wait for process to terminate
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()

                print("llama-server stopped")
            except Exception as e:
                print(f"Error stopping llama-server: {e}")
            finally:
                self.process = None
                self.is_running = False
                # Close log file if it was opened
                if hasattr(self, 'log_file') and self.log_file:
                    self.log_file.close()
                    self.log_file = None
                # Clean up old log files
                self._cleanup_old_logs()

    def get_server_info(self) -> Dict:
        """Get server information"""
        try:
            response = requests.get(f"{self.base_url}/props", timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Failed to get server info: {e}")
        return {}

    def create_chat_completion(self, messages: List[Dict], **kwargs) -> Dict:
        """Create a chat completion using the server API"""
        if not self.is_server_running():
            raise ConnectionError("llama-server is not running")

        payload = {
            "messages": messages,
            "stream": False,
            **kwargs
        }

        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                timeout=300  # 5 minute timeout for long generations
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            # Log the error for debugging
            error_msg = f"Failed to communicate with llama-server: {e}"
            print(f"[LLM Server Error] {error_msg}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"[LLM Server Error] Response status: {e.response.status_code}")
                try:
                    error_content = e.response.text
                    print(f"[LLM Server Error] Response content: {error_content[:500]}...")  # First 500 chars
                except Exception:
                    pass
            raise ConnectionError(error_msg)
    
    def _cleanup_old_logs(self):
        """Clean up old log files, keeping only the most recent 10"""
        try:
            # Get all log files in the logs directory
            log_files = [f for f in os.listdir(self.logs_dir) if f.startswith("llama_server_") and f.endswith(".log")]
            
            # Sort by modification time (oldest first)
            log_files.sort(key=lambda x: os.path.getmtime(os.path.join(self.logs_dir, x)))
            
            # Remove all but the most recent 10
            while len(log_files) > 10:
                oldest_file = log_files.pop(0)
                os.remove(os.path.join(self.logs_dir, oldest_file))
                print(f"Removed old log file: {oldest_file}")
        except Exception as e:
            print(f"Error during log cleanup: {e}")

class LocalModelManager:
    def __init__(self, models_dir: str = None):
        # Use application directory instead of user home to avoid Unicode path issues
        app_root = os.getcwd()
        self.models_dir = models_dir or os.path.join(app_root, "models")
        # Use local cache within the app directory
        self.cache_dir = os.path.join(self.models_dir, "hf_cache")
        self.config_file = os.path.join(self.models_dir, "models_config.json")
        self.ensure_directories()
        self.load_config()
        _import_hf_hub_and_wx()
        self.hf_api = _hf_api # Use the lazily imported HfApi

        # Initialize server manager
        self.server_manager = LlamaServerManager()

    def get_model_path(self, model_id: str) -> Optional[str]:
        """Get the local path of an installed model."""
        model_info = self.config.get("installed_models", {}).get(model_id)
        if model_info and "path" in model_info and os.path.exists(model_info["path"]):
            return model_info["path"]
        return None

    def ensure_directories(self):
        """Ensure necessary directories exist"""
        os.makedirs(self.models_dir, exist_ok=True)
        os.makedirs(os.path.join(self.cache_dir, "downloads"), exist_ok=True)


    def load_config(self):
        """Load model configuration"""
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
        else:
            self.config = {"installed_models": {}}
            self.save_config()

    def save_config(self):
        """Save model configuration"""
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)

    def get_available_models(self, query: str = "") -> List[Dict]:
        """Get list of available GGUF models from HuggingFace"""
        _import_hf_hub_and_wx() # Ensure HfApi is available
        if _hf_api is None:
            print("Hugging Face Hub API not available. Cannot fetch models.")
            return []
        try:
            # Prioritize GGUF in search query for more relevant results
            search_query = f"{query} GGUF"
            models = self.hf_api.list_models(
                search=search_query,
                sort="downloads",
                direction=-1,
                limit=50,
                filter="text-generation"
            )

            detailed_models = []
            for model in models:
                # Basic info
                model_info = {
                    "id": model.modelId,
                    "name": model.modelId,
                    "downloads": model.downloads,
                    "description": f"Author: {model.author}" if model.author else "Community Model",
                    "quantization": "Unknown",
                    "params": "Unknown"
                }

                # Try to extract more details from tags
                if model.tags:
                    # Search for quantization info like 'gguf-q4_k_m'
                    quant_tag = next((tag for tag in model.tags if 'gguf' in tag and ('q' in tag or 'Q' in tag)), None)
                    if quant_tag:
                        model_info["quantization"] = quant_tag.upper()

                    # Search for parameter size like '7b' or '7B'
                    params_tag = next((tag for tag in model.tags if 'b' in tag.lower() and tag.lower().replace('b','').replace('.','').isdigit()), None)
                    if params_tag:
                        model_info["params"] = f"{params_tag.upper()}"

                # Also try to extract info from the model name itself
                model_name_lower = model.modelId.lower()

                # Extract parameters from model name (e.g., "1b", "7b", "13b", "70b")
                param_match = re.search(r'(\d+(?:\.\d+)?)\s*b(?:illion)?', model_name_lower)
                if param_match and model_info["params"] == "Unknown":
                    model_info["params"] = f"{param_match.group(1)}B"

                # Extract quantization from model name or tags
                quant_patterns = [
                    r'q(\d+)_k_m', r'q(\d+)_k_s', r'q(\d+)_k_l',
                    r'q(\d+)_0', r'q(\d+)_1', r'q(\d+)',
                    r'fp16', r'fp32', r'int8', r'int4'
                ]

                for pattern in quant_patterns:
                    match = re.search(pattern, model_name_lower)
                    if match and model_info["quantization"] == "Unknown":
                        if pattern.startswith('q'):
                            model_info["quantization"] = f"Q{match.group(1)}"
                        else:
                            model_info["quantization"] = match.group(0).upper()
                        break

                detailed_models.append(model_info)

            return detailed_models

        except Exception as e:
            print(f"Error fetching available models: {e}")
            return []

    def get_installed_models(self) -> List[Dict]:
        """Get list of installed models from our config"""
        installed = []
        for model_id, info in self.config.get("installed_models", {}).items():
            # Verify the file still exists
            if os.path.exists(info.get("path", "")):
                installed.append({
                    "id": model_id,
                    "name": info.get("name", model_id),
                    "path": info.get("path"),
                    "installed_date": info.get("installed_date"),
                    "size": info.get("size", "Unknown")
                })
        return installed

    def list_repo_gguf_quants(self, model_id: str) -> List[str]:
        """
        Inspect a Hugging Face repository and return a list of quantization
        variants available as GGUF files (e.g., 'q4_k_m', 'q4_0', 'f16', 'int8').
        Returns an empty list if no GGUF files are found or on error.
        """
        _import_hf_hub_and_wx() # Ensure HfApi and inspect are available
        if _hf_api is None or _inspect is None:
            print("Hugging Face Hub API or inspect module not available. Cannot list quants.")
            return []
        try:
            # Check if timeout parameter is supported (added in huggingface_hub >= 0.20.0)
            list_repo_files_sig = _inspect.signature(self.hf_api.list_repo_files)
            supports_timeout = 'timeout' in list_repo_files_sig.parameters

            if supports_timeout:
                files_in_repo = self.hf_api.list_repo_files(repo_id=model_id, timeout=20)
            else:
                files_in_repo = self.hf_api.list_repo_files(repo_id=model_id)

            # Collect gguf filenames
            gguf_filenames = []
            for f in files_in_repo:
                if isinstance(f, str):
                    if f.lower().endswith('.gguf'):
                        gguf_filenames.append(f)
                else:
                    fname = getattr(f, 'rfilename', None) or getattr(f, 'filename', None) or getattr(f, 'path', None) or str(f)
                    if fname and fname.lower().endswith('.gguf'):
                        gguf_filenames.append(fname)

            if not gguf_filenames:
                return []

            # Extract quant tokens from filenames
            quant_set = set()
            quant_patterns = [
                (r'(q\d+_k_[a-z])', lambda m: m.group(1).lower()),  # q4_k_m, q4_k_s, etc.
                (r'(q\d+_0)', lambda m: m.group(1).lower()),
                (r'(q\d+_1)', lambda m: m.group(1).lower()),
                (r'(q\d+)', lambda m: m.group(1).lower()),
                (r'(fp16|fp32)', lambda m: m.group(1).lower()),
                (r'(int8|int4)', lambda m: m.group(1).lower()),
                (r'(-f16|-F16|_F16)', lambda m: 'f16'),
            ]

            for fname in gguf_filenames:
                fname_lower = fname.lower()
                matched = False
                for pattern, extractor in quant_patterns:
                    match = re.search(pattern, fname_lower)
                    if match:
                        quant_set.add(extractor(match))
                        matched = True
                        break
                if not matched:
                    # Try to find common substrings manually
                    if 'gguf' in fname_lower and 'q' in fname_lower:
                        # fallback: extract q<number> pattern
                        m = re.search(r'q(\d+)', fname_lower)
                        if m:
                            quant_set.add(f"q{m.group(1)}")

            # Normalize and sort results (prefer q-based then others)
            quants = sorted(list(quant_set), key=lambda s: (not s.startswith('q'), s))
            return quants

        except Exception as e:
            print(f"Error listing GGUF quants for {model_id}: {e}")
            return []

    def is_model_installed(self, model_id: str) -> bool:
        """Check if a model is registered as installed"""
        return model_id in self.config.get("installed_models", {})

    def download_model(self, model_id: str, model_name: str, progress_callback=None, max_retries: int = 3, preferred_quant: Optional[str] = None) -> bool:
        """Download a GGUF model file from a Hugging Face repository with improved error handling."""
        _import_hf_hub_and_wx() # Ensure wx and huggingface_hub are available
        if _wx is None or _hf_hub_download is None or _inspect is None:
            print("Dependencies for download not available.")
            if progress_callback:
                progress_callback(0, "Dependencies not available.")
            return False

        def progress_callback_wrapper(current: int, total: int, desc: str = ""):
            """Wrapper for progress callbacks to handle different formats"""
            if progress_callback:
                if total > 0:
                    percentage = int((current / total) * 90) + 10  # 10-100% range
                    _wx.CallAfter(progress_callback, percentage, f"{desc} ({current}/{total})")
                else:
                    _wx.CallAfter(progress_callback, 50, desc)

        def download_with_retry(attempt: int = 1) -> bool:
            """Download with retry logic and better error handling"""
            try:
                # Suppress common HuggingFace warnings that don't affect functionality
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=FutureWarning)
                    warnings.filterwarnings("ignore", category=DeprecationWarning)
                    warnings.filterwarnings("ignore", message=".*symlinks.*", category=UserWarning)

                    if progress_callback:
                        _wx.CallAfter(progress_callback, 5, f"Searching for GGUF files in {model_id}... (attempt {attempt}/{max_retries})")

                    # 1. Get the list of files in the repository
                    try:
                        # Check if timeout parameter is supported (added in huggingface_hub >= 0.20.0)
                        list_repo_files_sig = _inspect.signature(self.hf_api.list_repo_files)
                        supports_timeout = 'timeout' in list_repo_files_sig.parameters

                        if supports_timeout:
                            files_in_repo = self.hf_api.list_repo_files(repo_id=model_id, timeout=30)
                        else:
                            files_in_repo = self.hf_api.list_repo_files(repo_id=model_id)
                    except Exception as e:
                        raise Exception(f"Failed to access repository {model_id}: {str(e)}")

                    # 2. Find a GGUF file to download
                    # Support different return types from list_repo_files (strings or objects)
                    gguf_files = [f for f in files_in_repo if (isinstance(f, str) and f.lower().endswith(".gguf")) or (not isinstance(f, str) and (getattr(f, 'rfilename', '').lower().endswith('.gguf') or getattr(f, 'filename', '').lower().endswith('.gguf') or str(getattr(f, 'path', '')).lower().endswith('.gguf')))]
                    if not gguf_files:
                        raise Exception(f"No GGUF files found in the repository {model_id}")

                    # Build candidate tuples (original_obj, display_name, display_name_lower, size)
                    candidates = []
                    for f in gguf_files:
                        if isinstance(f, str):
                            fname = f
                            size = 0
                        else:
                            fname = getattr(f, 'rfilename', None) or getattr(f, 'filename', None) or getattr(f, 'path', None) or str(f)
                            size = getattr(f, 'size', 0) or 0
                        fname = fname or ""
                        fname_lower = fname.lower()
                        candidates.append((f, fname, fname_lower, size))

                    selected_candidate = None
                    # If preferred_quant is provided (and not Auto/Any), try to match filenames first
                    if preferred_quant and isinstance(preferred_quant, str) and preferred_quant.strip().lower() not in ('', 'auto', 'any'):
                        pq = preferred_quant.strip().lower()
                        matches = [c for c in candidates if pq in c[2]]
                        if matches:
                            # Choose the smallest matching file to keep deterministic behavior
                            matches.sort(key=lambda x: x[3] if isinstance(x[3], (int, float)) else 0)
                            selected_candidate = matches[0]

                    # Fallback: pick the smallest overall (existing behavior)
                    if not selected_candidate:
                        candidates.sort(key=lambda x: x[3] if isinstance(x[3], (int, float)) else 0)
                        selected_candidate = candidates[0]

                    filename_to_download = getattr(selected_candidate[0], 'rfilename', selected_candidate[1])

                    if progress_callback:
                        _wx.CallAfter(progress_callback, 10, f"Starting download of {filename_to_download}...")

                    # 3. Download the file with progress monitoring
                    try:
                        # Check if max_workers parameter is supported
                        hf_hub_download_sig = _inspect.signature(_hf_hub_download)
                        download_kwargs = {
                            "repo_id": model_id,
                            "filename": filename_to_download,
                            "cache_dir": self.cache_dir,
                            "resume_download": True,
                            "local_files_only": False,
                            "force_download": False,
                        }
                        
                        if 'max_workers' in hf_hub_download_sig.parameters:
                            download_kwargs["max_workers"] = 4  # Limit concurrent downloads
                        
                        local_path = _hf_hub_download(**download_kwargs)
                    except Exception as e:
                        if "symlinks" in str(e).lower():
                            # Try without symlinks if that's the issue
                            print("Symlink issue detected, retrying without symlink support...")
                            # Check if max_workers parameter is supported
                            hf_hub_download_sig = _inspect.signature(_hf_hub_download)
                            download_kwargs = {
                                "repo_id": model_id,
                                "filename": filename_to_download,
                                "cache_dir": self.cache_dir,
                                "resume_download": True,
                                "local_files_only": False,
                                "force_download": False,
                            }
                            
                            if 'max_workers' in hf_hub_download_sig.parameters:
                                download_kwargs["max_workers"] = 4  # Limit concurrent downloads
                            
                            local_path = _hf_hub_download(**download_kwargs)
                        else:
                            raise

                    # Verify the file was downloaded successfully
                    if not os.path.exists(local_path):
                        raise Exception(f"Download completed but file not found at {local_path}")

                    file_size = os.path.getsize(local_path)
                    if file_size == 0:
                        raise Exception("Downloaded file is empty")

                    if progress_callback:
                        _wx.CallAfter(progress_callback, 95, "Download complete. Verifying...")

                    # 4. Record the download in our config
                    self.config["installed_models"][model_id] = {
                        "name": model_name,
                        "installed_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "size": f"{file_size / 1e6:.2f} MB",
                        "path": local_path,
                        "filename": filename_to_download
                    }
                    self.save_config()

                    if progress_callback:
                        _wx.CallAfter(progress_callback, 100, "Model successfully installed!")

                    return True

            except Exception as e:
                error_msg = f"Download attempt {attempt} failed: {str(e)}"
                print(error_msg)

                if attempt < max_retries:
                    wait_time = attempt * 2  # Exponential backoff
                    print(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    return download_with_retry(attempt + 1)
                else:
                    # Final attempt failed
                    if progress_callback:
                        _wx.CallAfter(progress_callback, 0, f"Download failed after {max_retries} attempts")
                    return False

        def download_thread():
            """Main download thread with proper error handling"""
            try:
                success = download_with_retry()
                if progress_callback:
                    if success:
                        _wx.CallAfter(progress_callback, 100, "Installation complete!")
                    else:
                        _wx.CallAfter(progress_callback, 0, "Download failed")
                self.download_result = success

            except Exception as e:
                error_msg = f"Critical error during download: {str(e)}"
                print(error_msg)
                if progress_callback:
                    _wx.CallAfter(progress_callback, 0, f"Error: {str(e)}")
                self.download_result = False

            finally:
                self.download_event.set()

        # Initialize download state
        self.download_result = None
        self.download_event = threading.Event()

        # Start download in background thread
        download_thread_obj = threading.Thread(target=download_thread, daemon=True)
        download_thread_obj.start()

        return True

    def download_complete(self, success: bool):
        """Callback to signal download completion."""
        self.download_result = success
        self.download_event.set()

    def uninstall_model(self, model_id: str) -> bool:
        """Uninstall a model by removing it from the config and deleting the file."""
        try:
            if model_id in self.config["installed_models"]:
                model_info = self.config["installed_models"][model_id]
                model_path = model_info.get("path")

                # Remove from config first
                del self.config["installed_models"][model_id]
                self.save_config()

                if model_path and os.path.exists(model_path):
                    try:
                        os.remove(model_path)
                        print(f"Removed file: {model_path}")
                        # Optionally, clean up empty directories in the cache
                    except OSError as e:
                        print(f"Error removing file {model_path}: {e}")

                return True
            return False
        except Exception as e:
            print(f"Error uninstalling model {model_id}: {e}")
            return False

    def start_model_server(self, model_id: str, context_size: int = 4096, gpu_layers: int = -1) -> bool:
        """Start a server for the specified model using llama-server.exe"""
        model_path = self.get_model_path(model_id)
        if not model_path:
            raise ValueError(f"Model '{model_id}' not found. Please download it first.")

        return self.server_manager.start_server(model_path, context_size, gpu_layers)

    def stop_model_server(self):
        """Stop the current model server"""
        self.server_manager.stop_server()

    def is_model_server_running(self) -> bool:
        """Check if the model server is running"""
        return self.server_manager.is_server_running()

    def get_model_server_info(self) -> Dict:
        """Get information about the running model server"""
        return self.server_manager.get_server_info()

    def create_chat_completion(self, messages: List[Dict], **kwargs) -> Dict:
        """Create a chat completion using the model server"""
        return self.server_manager.create_chat_completion(messages, **kwargs)