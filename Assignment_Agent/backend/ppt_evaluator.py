"""
PPT Evaluator - Evaluate PowerPoint presentations using AI
"""
import json
import logging
from typing import Dict, List, Optional
from openrouter_service import OpenRouterService

logger = logging.getLogger(__name__)


class PPTEvaluator:
    """Evaluate PowerPoint presentations based on text content and structure"""
    
    def __init__(self, openrouter_service: OpenRouterService):
        self.openrouter_service = openrouter_service
    
    def build_evaluation_prompt(self, title: str, description: str, total_slides: int, slides_text: str) -> str:
        """
        Build the evaluation prompt for PPT files
        Uses the specific template provided
        """
        prompt = f"""You are an expert presentation evaluator. Analyze PowerPoint presentations based on their text content and structure.
Evaluate ONLY based on the text content provided - do NOT evaluate design or visuals.
Return ONLY valid JSON, no other text.

Evaluate this PowerPoint presentation on text content, structure, and title alignment.

**Presentation Metadata:**
- Title: {title}
- Description: {description}
- Total Slides: {total_slides}

**Slide Content:**
{slides_text}

Evaluate across these criteria and respond with ONLY this JSON (no markdown, no extra text):

{{
    "content_quality": {{
        "score": <0-100>,
        "feedback": "<2-3 sentence feedback on accuracy, relevance, depth, research quality>"
    }},
    "structure": {{
        "score": <0-100>,
        "feedback": "<2-3 sentence feedback on logical flow, hierarchy, transitions, organization>"
    }},
    "alignment": {{
        "score": <0-100>,
        "feedback": "<2-3 sentence feedback on how well content matches title and description>"
    }},
    "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
    "improvements": ["<improvement 1>", "<improvement 2>", "<improvement 3>"],
    "summary": "<1-2 sentence overall summary>"
}}
"""
        return prompt
    
    def parse_evaluation_response(self, response_text: str) -> Dict:
        """
        Parse the AI response and extract JSON
        Handles cases where response might have markdown or extra text
        """
        try:
            # Try to find JSON in the response
            response_text = response_text.strip()
            
            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                # Find the first ``` and last ```
                start_idx = response_text.find('```')
                if start_idx != -1:
                    # Check if there's a language identifier
                    end_of_first_line = response_text.find('\n', start_idx)
                    if end_of_first_line != -1:
                        response_text = response_text[end_of_first_line + 1:]
                
                # Find the last ```
                last_idx = response_text.rfind('```')
                if last_idx != -1:
                    response_text = response_text[:last_idx]
            
            # Try to find JSON object boundaries
            start_brace = response_text.find('{')
            end_brace = response_text.rfind('}')
            
            if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
                json_text = response_text[start_brace:end_brace + 1]
                result = json.loads(json_text)
                return result
            else:
                # Try parsing the whole response
                result = json.loads(response_text)
                return result
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from response: {e}")
            logger.debug(f"Response text: {response_text[:500]}")
            # Return error structure
            return {
                "error": "Failed to parse evaluation response",
                "raw_response": response_text[:500]
            }
    
    def evaluate_ppt(self, title: str, description: str, ppt_data: Dict[str, any]) -> Dict:
        """
        Evaluate a single PPT file
        ppt_data should contain: slides_text, total_slides, filename
        """
        try:
            slides_text = ppt_data.get('slides_text', '')
            total_slides = ppt_data.get('total_slides', 0)
            filename = ppt_data.get('filename', 'Unknown')
            
            # Check for actual errors (library not available, reading errors)
            error_indicators = [
                '[python-pptx library not available',
                '[Error reading PPTX file',
                '[Error reading PPT file',
                '[Error opening PowerPoint',
                '[comtypes library not available',
                '[Unsupported PowerPoint format'
            ]
            
            is_error = any(indicator in slides_text for indicator in error_indicators)
            
            if not slides_text or is_error:
                error_msg = slides_text if is_error else "No text content extracted"
                return {
                    "error": f"Could not extract text from PPT file: {filename}. {error_msg}",
                    "filename": filename
                }
            
            # Allow "[No text content found in slides]" - this is valid (empty slides)
            # but we should still try to evaluate if there are slides
            if total_slides == 0 and "[No text content found in slides]" in slides_text:
                return {
                    "error": f"PPT file {filename} has no slides or no extractable text content",
                    "filename": filename
                }
            
            # Build prompt
            prompt = self.build_evaluation_prompt(title, description, total_slides, slides_text)
            
            # Call OpenRouter service
            result = self.openrouter_service.generate(prompt, system_message="You are an expert presentation evaluator. Return ONLY valid JSON, no other text.")
            
            if not result.get("success"):
                return {
                    "error": result.get("error", "No response from AI service"),
                    "filename": filename
                }
            
            response_text = result.get("response", "")
            if not response_text:
                return {
                    "error": "Empty response from AI service",
                    "filename": filename
                }
            
            # Parse response
            evaluation_result = self.parse_evaluation_response(response_text)
            
            # Add filename to result
            evaluation_result['filename'] = filename
            evaluation_result['total_slides'] = total_slides
            
            return evaluation_result
            
        except Exception as e:
            logger.error(f"Error evaluating PPT: {e}", exc_info=True)
            return {
                "error": f"Error during evaluation: {str(e)}",
                "filename": ppt_data.get('filename', 'Unknown')
            }
    
    def evaluate_multiple_ppts(self, title: str, description: str, ppt_files_data: List[Dict[str, any]]) -> Dict:
        """
        Evaluate multiple PPT files
        Returns a dict with results for each file
        """
        results = {
            "title": title,
            "description": description,
            "evaluations": []
        }
        
        for ppt_data in ppt_files_data:
            evaluation = self.evaluate_ppt(title, description, ppt_data)
            results["evaluations"].append(evaluation)
        
        return results
    
    def format_evaluation_result(self, evaluation_result: Dict) -> str:
        """
        Format evaluation result as readable text
        """
        if "error" in evaluation_result:
            return f"Error: {evaluation_result.get('error', 'Unknown error')}"
        
        parts = []
        parts.append(f"File: {evaluation_result.get('filename', 'Unknown')}")
        parts.append(f"Total Slides: {evaluation_result.get('total_slides', 0)}")
        parts.append("")
        
        # Content Quality
        if "content_quality" in evaluation_result:
            cq = evaluation_result["content_quality"]
            parts.append(f"Content Quality Score: {cq.get('score', 'N/A')}/100")
            parts.append(f"Feedback: {cq.get('feedback', 'N/A')}")
            parts.append("")
        
        # Structure
        if "structure" in evaluation_result:
            struct = evaluation_result["structure"]
            parts.append(f"Structure Score: {struct.get('score', 'N/A')}/100")
            parts.append(f"Feedback: {struct.get('feedback', 'N/A')}")
            parts.append("")
        
        # Alignment
        if "alignment" in evaluation_result:
            align = evaluation_result["alignment"]
            parts.append(f"Alignment Score: {align.get('score', 'N/A')}/100")
            parts.append(f"Feedback: {align.get('feedback', 'N/A')}")
            parts.append("")
        
        # Strengths
        if "strengths" in evaluation_result:
            parts.append("Strengths:")
            for strength in evaluation_result["strengths"]:
                parts.append(f"  - {strength}")
            parts.append("")
        
        # Improvements
        if "improvements" in evaluation_result:
            parts.append("Areas for Improvement:")
            for improvement in evaluation_result["improvements"]:
                parts.append(f"  - {improvement}")
            parts.append("")
        
        # Summary
        if "summary" in evaluation_result:
            parts.append(f"Summary: {evaluation_result['summary']}")
        
        return "\n".join(parts)

