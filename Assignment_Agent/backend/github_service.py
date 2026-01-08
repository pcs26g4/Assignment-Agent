"""
GitHub repository file fetching service
Fetches all files from a public GitHub repository recursively
"""
import os
import requests
import base64
from pathlib import Path
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class GitHubService:
    """Service to fetch files from GitHub repositories"""
    
    # File extensions to include (code files)
    CODE_EXTENSIONS = {
        '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.cpp', '.c', '.h', '.hpp',
        '.cs', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.dart', '.r', '.m',
        '.scala', '.clj', '.hs', '.elm', '.ex', '.exs', '.erl', '.ml', '.fs',
        '.vue', '.svelte', '.html', '.css', '.scss', '.sass', '.less', '.json',
        '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.sh', '.bat',
        '.ps1', '.sql', '.md', '.txt', '.log', '.env', '.gitignore', '.dockerfile',
        '.dockerignore', '.makefile', '.cmake', '.gradle', '.maven', '.pom'
    }
    
    # Directories to skip
    SKIP_DIRS = {
        '.git', 'node_modules', '__pycache__', '.pytest_cache', '.venv', 'venv',
        'env', '.env', 'dist', 'build', '.next', '.nuxt', '.cache', 'coverage',
        '.idea', '.vscode', '.vs', 'target', 'bin', 'obj', '.gradle', '.mvn'
    }
    
    def __init__(self):
        self.github_token = os.getenv('GITHUB_TOKEN', '')
        self.base_url = 'https://api.github.com'
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with optional token"""
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitHub-File-Fetcher'
        }
        if self.github_token:
            headers['Authorization'] = f'token {self.github_token}'
        return headers
    
    def _parse_github_url(self, url: str) -> Optional[tuple]:
        """Parse GitHub URL to extract owner and repo"""
        try:
            # Remove trailing slash and .git if present
            url = url.rstrip('/').rstrip('.git')
            
            # Extract owner/repo from URL
            if 'github.com' in url:
                parts = url.split('github.com/')
                if len(parts) > 1:
                    path = parts[1].strip('/')
                    path_parts = path.split('/')
                    if len(path_parts) >= 2:
                        owner = path_parts[0]
                        repo = path_parts[1]
                        # Remove any query params or fragments
                        repo = repo.split('?')[0].split('#')[0]
                        return (owner, repo)
        except Exception as e:
            logger.error(f"Error parsing GitHub URL {url}: {e}")
        return None
    
    def _fetch_file_content(self, owner: str, repo: str, path: str) -> Optional[str]:
        """Fetch content of a single file from GitHub"""
        try:
            url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('type') == 'file' and data.get('encoding') == 'base64':
                    content = base64.b64decode(data['content']).decode('utf-8', errors='replace')
                    return content
            elif response.status_code == 404:
                logger.warning(f"File not found: {path}")
            else:
                logger.warning(f"Failed to fetch {path}: {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching file {path}: {e}")
        return None
    
    def _fetch_tree_recursive(self, owner: str, repo: str, path: str = '', branch: str = 'main') -> List[Dict]:
        """Recursively fetch all files from GitHub repository"""
        files = []
        
        try:
            # First, get the default branch if not provided
            if not branch or branch == 'main':
                repo_info_url = f"{self.base_url}/repos/{owner}/{repo}"
                repo_response = requests.get(repo_info_url, headers=self._get_headers(), timeout=30)
                if repo_response.status_code == 200:
                    branch = repo_response.json().get('default_branch', 'main')
            
            # Fetch contents of current directory
            contents_url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}" if path else f"{self.base_url}/repos/{owner}/{repo}/contents"
            params = {'ref': branch} if branch else {}
            response = requests.get(contents_url, headers=self._get_headers(), params=params, timeout=30)
            
            if response.status_code != 200:
                logger.warning(f"Failed to fetch contents from {path}: {response.status_code}")
                return files
            
            items = response.json()
            if not isinstance(items, list):
                items = [items]
            
            for item in items:
                item_path = item.get('path', '')
                item_name = item.get('name', '')
                item_type = item.get('type', '')
                
                # Skip directories we don't want
                if item_type == 'dir' and item_name.lower() in self.SKIP_DIRS:
                    continue
                
                # If it's a directory, recurse
                if item_type == 'dir':
                    sub_files = self._fetch_tree_recursive(owner, repo, item_path, branch)
                    files.extend(sub_files)
                
                # If it's a file, check if we want to include it
                elif item_type == 'file':
                    file_ext = Path(item_name).suffix.lower()
                    # Include code files and text files
                    if file_ext in self.CODE_EXTENSIONS or not file_ext:
                        file_content = self._fetch_file_content(owner, repo, item_path)
                        if file_content is not None:
                            files.append({
                                'path': item_path,
                                'name': item_name,
                                'content': file_content,
                                'size': item.get('size', 0)
                            })
                            logger.info(f"Fetched file: {item_path}")
        
        except Exception as e:
            logger.error(f"Error fetching tree from {path}: {e}")
        
        return files
    
    def fetch_repository_files(self, github_url: str, max_files: int = 100) -> List[Dict]:
        """
        Fetch all relevant files from a GitHub repository
        
        Args:
            github_url: GitHub repository URL
            max_files: Maximum number of files to fetch (default: 100)
        
        Returns:
            List of file dictionaries with path, name, content, and size
        """
        parsed = self._parse_github_url(github_url)
        if not parsed:
            logger.error(f"Invalid GitHub URL: {github_url}")
            return []
        
        owner, repo = parsed
        logger.info(f"Fetching files from {owner}/{repo}")
        
        try:
            files = self._fetch_tree_recursive(owner, repo)
            
            # Limit number of files
            if len(files) > max_files:
                logger.warning(f"Repository has {len(files)} files, limiting to {max_files}")
                files = files[:max_files]
            
            logger.info(f"Successfully fetched {len(files)} files from {owner}/{repo}")
            return files
        
        except Exception as e:
            logger.error(f"Error fetching repository files: {e}")
            return []




