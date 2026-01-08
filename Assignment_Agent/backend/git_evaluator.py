"""
Git Repository Evaluator
Evaluates GitHub repositories and provides project information, purpose, and details
"""
import os
import json
import re
from typing import List, Dict, Optional
import logging


logger = logging.getLogger(__name__)



class GitEvaluator:
    """Service to evaluate Git repositories and provide project insights"""
    
    def __init__(self, openrouter_service):
        self.openrouter_service = openrouter_service

    # ------------------------------------------------------------------
    # PROJECT INFORMATION (existing behaviour)
    # ------------------------------------------------------------------
    def build_evaluation_prompt(self, github_url: str, files: List[Dict]) -> str:
        """
        Build a prompt specifically for Git repository evaluation
        This is separate from the grading prompt used for file uploads
        """
        # Calculate total content size
        total_content_size = sum(len(f.get('content', '')) for f in files)
        
        # Limit per file and total content to avoid token limits
        per_file_limit = int(os.getenv("GIT_EVAL_PER_FILE_CHAR_LIMIT", "15000"))
        total_limit = int(os.getenv("GIT_EVAL_TOTAL_CHAR_LIMIT", "100000"))
        
        # Prepare file contents with truncation
        prepared_files = []
        current_total = 0
        
        for file_info in files:
            content = file_info.get('content', '')
            if not isinstance(content, str):
                content = str(content)
            
            # Truncate individual file if too long
            truncated_note = ""
            if len(content) > per_file_limit:
                overflow = len(content) - per_file_limit
                content = content[:per_file_limit]
                truncated_note = f"\n[TRUNCATED {overflow} chars due to per-file limit]"
            
            # Check if adding this file would exceed total limit
            if current_total + len(content) > total_limit and prepared_files:
                logger.warning(f"Reached total content limit, stopping at {len(prepared_files)} files")
                break
            
            prepared_files.append({
                'path': file_info.get('path', ''),
                'name': file_info.get('name', ''),
                'content': f"{content}{truncated_note}",
                'size': file_info.get('size', 0)
            })
            current_total += len(content)
        
        # Build the evaluation prompt - AUTO-DETECTION ONLY (NO ASSUMPTIONS)
        prompt_parts = [
            f"Analyze this GitHub repository: {github_url}\n\n",

            "You are an expert software project analyst.\n",
            "You will be given a list of ALL repository files with their contents, including nested files.\n",
            "Carefully read EVERY provided file (code, configs, docs), not just the README.\n\n",

            "Your task is to DESCRIBE what the repository ACTUALLY contains.\n",
            "Do NOT assume any technologies, architecture, or features unless they are clearly visible in code or config files.\n",
            "Do NOT invent backend, frontend, database, or frameworks.\n\n",

            "Return ONLY a JSON object with these EXACT 5 fields:\n\n",

            "1. project_about (string)\n",
            "   - 1–3 sentences describing what the project is about, based ONLY on the code and files.\n",
            "   - If the purpose is unclear, briefly state that it cannot be fully determined.\n\n",

            "2. project_use (string)\n",
            "   - Short explanation of how the project is intended to be used.\n",
            "   - If usage is unclear, return an empty string.\n\n",

            "3. technology_stack (array of strings)\n",
            "   - List ONLY technologies, frameworks, libraries, and languages that are clearly detected from files.\n",
            "   - Use evidence such as package.json, requirements.txt, imports, configs, or build files.\n",
            "   - If a technology is not clearly present, DO NOT include it.\n\n",

            "4. features (array of strings)\n",
            "   - List observable features or functionalities implemented in the code.\n",
            "   - Each item should be concise and factual.\n",
            "   - If features are unclear, return an empty array.\n\n",

            "5. project_structure (string)\n",
            "   - Describe how the repository is organized based on folders and files.\n",
            "   - Mention important directories only if they actually exist (e.g., backend/, frontend/, src/, api/).\n\n",

            "Guidelines:\n",
            "- Analyze ALL provided files, including nested directories.\n",
            "- Prefer concrete facts from code and configuration over guesses.\n",
            "- If information cannot be determined, use empty string \"\" or empty array [].\n",
            "- Do NOT include markdown, comments, explanations, or extra fields.\n",
            "- Respond with ONLY valid JSON.\n\n",

            "The JSON MUST follow this exact structure:\n",
            "{\n",
            '  "project_about": "",\n',
            '  "project_use": "",\n',
            '  "technology_stack": [],\n',
            '  "features": [],\n',
            '  "project_structure": ""\n',
            "}\n\n",

            "Repository files to analyze:\n\n",
        ]
        
        # Add file contents
        for file_info in prepared_files:
            prompt_parts.append(f"--- File: {file_info['path']} ({file_info['name']}) ---\n")
            prompt_parts.append(file_info['content'])
            prompt_parts.append("\n\n")
        
        return "".join(prompt_parts)
    
    def evaluate_repository(self, github_url: str, files: List[Dict]) -> Dict:
        """
        Evaluate a GitHub repository and return analysis results
        
        Args:
            github_url: The GitHub repository URL
            files: List of file dictionaries from GitHubService
            
        Returns:
            Dictionary with evaluation results
        """
        if not files:
            return {
                "success": False,
                "error": "No files found in repository",
                "result": None
            }
        
        try:
            # Build the evaluation prompt
            prompt = self.build_evaluation_prompt(github_url, files)
            
            # Generate evaluation using OpenRouter with project analysis system message
            # This is DIFFERENT from the grading system message used for file uploads
            system_message = "You are an expert software project analyst. Analyze GitHub repositories and provide comprehensive project information. Return your analysis as JSON only."
            logger.info(f"Evaluating repository {github_url} with {len(files)} files")
            result = self.openrouter_service.generate(prompt, system_message=system_message)
            
            if not result.get("success"):
                return {
                    "success": False,
                    "error": result.get("error", "Failed to generate evaluation"),
                    "result": None
                }
            
            raw_response = result.get("response", "")
            
            # Try to parse JSON from response
            evaluation_data = None
            try:
                evaluation_data = json.loads(raw_response)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code blocks or text
                try:
                    # Look for JSON in code blocks
                    json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*\})\s*```', raw_response)
                    if json_match:
                        evaluation_data = json.loads(json_match.group(1))
                    else:
                        # Try to find JSON object in the text
                        json_match = re.search(r'\{[\s\S]*\}', raw_response)
                        if json_match:
                            evaluation_data = json.loads(json_match.group(0))
                except Exception as e:
                    logger.warning(f"Failed to parse JSON from response: {e}")
                    # If parsing fails, create a structured response with the raw text
                    evaluation_data = {
                        "project_purpose": "Unable to parse structured response",
                        "evaluation_summary": raw_response[:2000] if raw_response else "No response generated",
                        "raw_response": raw_response
                    }
            
            # Ensure required fields exist with default values
            if not isinstance(evaluation_data, dict):
                evaluation_data = {}
            
            # Ensure all required fields are present with defaults
            required_fields = {
                "project_about": "",
                "project_use": "",
                "technology_stack": [],
                "features": [],
                "project_structure": ""
            }
            
            for field, default_value in required_fields.items():
                if field not in evaluation_data:
                    evaluation_data[field] = default_value
                # Ensure correct types
                if field in ["technology_stack", "features"] and not isinstance(evaluation_data[field], list):
                    evaluation_data[field] = []
                elif field not in ["technology_stack", "features"] and not isinstance(evaluation_data[field], str):
                    evaluation_data[field] = str(evaluation_data[field]) if evaluation_data[field] else ""
            
            return {
                "success": True,
                "result": evaluation_data,
                "raw_response": raw_response
            }
            
        except Exception as e:
            logger.error(f"Error evaluating repository: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Error during evaluation: {str(e)}",
                "result": None
            }

    # ------------------------------------------------------------------
    # GRADING AGAINST USER RULES (new behaviour)
    # ------------------------------------------------------------------
    def build_grading_prompt(self, github_url: str, files: List[Dict], description: str) -> str:
        """
        Build a prompt for grading a GitHub repository against user-provided rules.

        The description is treated as the source of truth for expected technologies,
        architecture and other rules. The model must:
        - Extract clear rules from the description
        - Analyze the repository files
        - Check which rules are satisfied or violated
        - Pay special attention to technology_stack mismatches (e.g. backend stack)
        """
        # Reuse the same content limiting logic as normal evaluation
        per_file_limit = int(os.getenv("GIT_EVAL_PER_FILE_CHAR_LIMIT", "15000"))
        total_limit = int(os.getenv("GIT_EVAL_TOTAL_CHAR_LIMIT", "100000"))

        prepared_files = []
        current_total = 0

        for file_info in files:
            content = file_info.get('content', '')
            if not isinstance(content, str):
                content = str(content)

            truncated_note = ""
            if len(content) > per_file_limit:
                overflow = len(content) - per_file_limit
                content = content[:per_file_limit]
                truncated_note = f"\n[TRUNCATED {overflow} chars due to per-file limit]"

            if current_total + len(content) > total_limit and prepared_files:
                logger.warning(f"Reached total content limit (grading), stopping at {len(prepared_files)} files")
                break

            prepared_files.append({
                'path': file_info.get('path', ''),
                'name': file_info.get('name', ''),
                'content': f"{content}{truncated_note}",
                'size': file_info.get('size', 0)
            })
            current_total += len(content)

        # Check if description is actually empty (after stripping)
        description_clean = description.strip() if description else ""
        has_description = bool(description_clean)
        
        prompt_parts = [
            f"Analyze this GitHub repository: {github_url}\n\n",
        ]
        
        if has_description:
            prompt_parts.extend([
                "The user has provided a description that contains RULES / REQUIREMENTS for the project.\n",
                "You must grade the ACTUAL repository implementation against those rules.\n\n",
                "User-provided description / rules (treat these as the expected specification):\n",
                "--------------------\n",
                description_clean,
                "\n--------------------\n\n",
            ])
        else:
            prompt_parts.append(
                "CRITICAL: The description section above is EMPTY. DO NOT create any default rules.\n"
                "DO NOT use any example rules from the JSON schema below.\n"
                "Return an error message indicating that no rules were provided.\n\n"
            )
        
        prompt_parts.extend([
            "You are an expert full‑stack architect and strict grader.\n",
            "Carefully read ALL repository files below (code + configs + docs).\n",
        ])
        
        if has_description:
            prompt_parts.extend([
                "Then perform ALL of the following:\n",
                "1. Extract a clear list of individual rules from the description above.\n",
                "   - Each rule should be short and testable.\n",
                "   - Include technology rules, architectural rules, feature rules, security rules, etc.\n",
                "   - Extract ONLY rules that are explicitly stated in the description.\n",
                "   - DO NOT invent or assume rules that are not in the description.\n",
                "2. For EACH extracted rule, check whether the repository actually follows it.\n",
                "   - Base your judgement ONLY on the real code and configuration.\n",
                "   - If evidence is unclear or missing, treat the rule as NOT satisfied and explain why.\n",
                "3. Pay special attention to technology stack claims.\n",
                "   - Detect the REAL technology stack from code (backend and frontend separately if possible).\n",
                "   - If the description claims a backend tech stack but the code uses something else,\n",
                "     flag this as a violation and clearly state what is used.\n",
                "4. Compute an overall score_percent between 0 and 100 based on how many rules are satisfied\n",
                "   and the severity of violations.\n\n",
            ])
        else:
            prompt_parts.extend([
                "Since no description/rules were provided, you should return an error response.\n",
                "DO NOT grade the repository or create any rules.\n\n",
            ])
        
        prompt_parts.extend([
            "Return ONLY valid JSON (no markdown, no comments) with this exact schema:\n",
            "{\n",
            '  "rules_summary": "Short summary of what the rules are about",\n',
            '  "overall_comment": "High-level explanation of how well the repo matches the rules",\n',
            '  "score_percent": 87.5,\n',
            '  "detected_technology_stack": ["Python", "FastAPI", "PostgreSQL"],\n',
            '  "rule_results": [\n',
            "    {\n",
            '      "rule_text": "example rule from description",\n',
            '      "is_satisfied": true,\n',
            '      "severity": "critical",\n',
            '      "evidence": "For example, mention key files or configs that prove it.",\n',
            '      "failure_reason": ""\n',
            "    }\n",
            "  ],\n",
            '  "technology_mismatch": {\n',
            '    "expected_from_description": "example expected tech stack from description",\n',
            '    "actual_from_code": "actual tech stack detected from code",\n',
            '    "has_mismatch": true,\n',
            '    "details": "Explain clearly what was expected vs what is implemented."\n',
            "  }\n",
            "}\n\n",
            "CRITICAL INSTRUCTIONS:\n",
            "- The JSON schema above is ONLY an EXAMPLE. DO NOT use the example values as actual rules.\n",
            "- Extract rules ONLY from the description section provided above.\n",
            "- If the description is empty or contains no rules, return an error in overall_comment:\n",
            '  "Error: No rules or description provided. Please provide grading rules in the description field."\n',
            "- Do NOT invent technologies that you do not see in code or configs.\n",
            "- Do NOT create default rules if the description is empty.\n",
            "- If you cannot determine something from the repository, mark the corresponding rule as not satisfied\n",
            "  and explain that the evidence is missing.\n\n",
            "Repository files to analyze:\n\n",
        ])

        for file_info in prepared_files:
            prompt_parts.append(f"--- File: {file_info['path']} ({file_info['name']}) ---\n")
            prompt_parts.append(file_info['content'])
            prompt_parts.append("\n\n")

        return "".join(prompt_parts)

    def grade_repository(self, github_url: str, files: List[Dict], description: str) -> Dict:
        """
        Grade a GitHub repository against user-provided rules/description.

        This is separate from the simple project information evaluation.

        Returns:
            {
              "success": bool,
              "result": { ...parsed JSON... } | None,
              "raw_response": str | None,
              "error": str | None
            }
        """
        if not files:
            return {
                "success": False,
                "error": "No files found in repository",
                "result": None,
                "raw_response": None,
            }

        if not description or not description.strip():
            return {
                "success": False,
                "error": "Description with grading rules is required",
                "result": None,
                "raw_response": None,
            }

        try:
            prompt = self.build_grading_prompt(github_url, files, description)

            system_message = (
                "You are a strict software project grader. "
                "You MUST return ONLY valid JSON that grades the repository against the user's rules."
            )
            logger.info(f"Grading repository {github_url} against user rules")
            result = self.openrouter_service.generate(prompt, system_message=system_message)

            if not result.get("success"):
                return {
                    "success": False,
                    "error": result.get("error", "Failed to generate grading result"),
                    "result": None,
                    "raw_response": result.get("response"),
                }

            raw_response = result.get("response", "")

            grading_data = None
            try:
                grading_data = json.loads(raw_response)
            except json.JSONDecodeError:
                try:
                    json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*\})\s*```', raw_response)
                    if json_match:
                        grading_data = json.loads(json_match.group(1))
                    else:
                        json_match = re.search(r'\{[\s\S]*\}', raw_response)
                        if json_match:
                            grading_data = json.loads(json_match.group(0))
                except Exception as e:
                    logger.warning(f"Failed to parse grading JSON from response: {e}")
                    grading_data = None

            if not isinstance(grading_data, dict):
                grading_data = {}

            # Ensure important fields exist with reasonable defaults
            defaults = {
                "rules_summary": "",
                "overall_comment": "",
                "score_percent": 0.0,
                "detected_technology_stack": [],
                "rule_results": [],
                "technology_mismatch": {
                    "expected_from_description": "",
                    "actual_from_code": "",
                    "has_mismatch": False,
                    "details": "",
                },
            }

            for key, default_val in defaults.items():
                if key not in grading_data:
                    grading_data[key] = default_val

            # Type safety
            if not isinstance(grading_data.get("detected_technology_stack"), list):
                grading_data["detected_technology_stack"] = []
            if not isinstance(grading_data.get("rule_results"), list):
                grading_data["rule_results"] = []
            if not isinstance(grading_data.get("score_percent"), (int, float)):
                try:
                    grading_data["score_percent"] = float(grading_data["score_percent"])
                except Exception:
                    grading_data["score_percent"] = 0.0

            tech_mismatch = grading_data.get("technology_mismatch")
            if not isinstance(tech_mismatch, dict):
                grading_data["technology_mismatch"] = defaults["technology_mismatch"]
            else:
                for k, v in defaults["technology_mismatch"].items():
                    if k not in tech_mismatch:
                        tech_mismatch[k] = v
                grading_data["technology_mismatch"] = tech_mismatch

            return {
                "success": True,
                "result": grading_data,
                "raw_response": raw_response,
            }

        except Exception as e:
            logger.error(f"Error grading repository: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Error during grading: {str(e)}",
                "result": None,
                "raw_response": None,
            }
