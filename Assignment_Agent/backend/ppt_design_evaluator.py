"""
PPT Design Evaluator - Evaluate PowerPoint presentation visual design using vision AI
"""
import json
import logging
import base64
import io
from typing import Dict, List, Optional
from pathlib import Path
from .openrouter_service import OpenRouterService

logger = logging.getLogger(__name__)


class PPTDesignEvaluator:
    """Evaluate PowerPoint presentation visual design based on slide images"""
    
    def __init__(self, openrouter_service: OpenRouterService):
        self.openrouter_service = openrouter_service
    
    def build_design_evaluation_prompt_from_metadata(self, design_description: str, filename: str, total_slides: int) -> str:
        """
        Build the design evaluation prompt from design metadata
        Returns prompt text for text-based AI model
        """
        prompt_text = f"""You are an expert presentation design evaluator. Analyze PowerPoint presentation design based on extracted design metadata.
Evaluate layout, color consistency, typography, visual hierarchy, and overall visual appeal.
Do NOT evaluate text content - only visual design aspects.
Return ONLY valid JSON, no other text.

**Presentation:** {filename}
**Total Slides:** {total_slides}

**Design Metadata:**
{design_description}

Evaluate the design and visual quality of this PowerPoint presentation based on the design metadata provided above.

Focus on:
- Visual clarity and readability (based on layout, shape positioning, spacing)
- Layout and balance (based on shape distribution, positioning, sizes)
- Color consistency and harmony (based on color usage across slides)
- Typography and font usage (based on font choices, sizes, styles)
- Visual hierarchy and spacing (based on shape positioning and sizes)
- Overall design coherence (consistency across slides)

Respond with ONLY this JSON (no markdown, no extra text):

{{
    "visual_clarity": {{
        "score": <0-100>,
        "feedback": "<brief feedback on readability and visual clarity>"
    }},
    "layout_balance": {{
        "score": <0-100>,
        "feedback": "<brief feedback on slide layout and spatial balance>"
    }},
    "color_consistency": {{
        "score": <0-100>,
        "feedback": "<brief feedback on color scheme and consistency>"
    }},
    "typography": {{
        "score": <0-100>,
        "feedback": "<brief feedback on fonts, sizes, hierarchy>"
    }},
    "visual_appeal": {{
        "score": <0-100>,
        "feedback": "<brief feedback on overall visual design quality>"
    }},
    "design_strengths": ["<strength 1>", "<strength 2>"],
    "design_improvements": ["<improvement 1>", "<improvement 2>"],
    "design_summary": "<1-2 sentence summary of design quality>"
}}
"""
        return prompt_text
    
    def build_design_evaluation_prompt(self, slide_images_base64: List[str]) -> tuple[str, List[Dict]]:
        """
        Build the design evaluation prompt with images (legacy method - kept for backward compatibility)
        Returns (prompt_text, messages_with_images)
        """
        prompt_text = """You are an expert presentation design evaluator. Analyze slide images for visual design quality.
Evaluate layout, color consistency, typography, visual hierarchy, and overall visual appeal.
Do NOT evaluate text content - only visual design aspects.
Return ONLY valid JSON, no other text.

Evaluate the design and visual quality of these PowerPoint slides.

Focus on:
- Visual clarity and readability
- Layout and balance
- Color consistency and harmony
- Typography and font usage
- Visual hierarchy and spacing
- Image quality and placement

Respond with ONLY this JSON (no markdown, no extra text):

{
    "visual_clarity": {
        "score": <0-100>,
        "feedback": "<brief feedback on readability and visual clarity>"
    },
    "layout_balance": {
        "score": <0-100>,
        "feedback": "<brief feedback on slide layout and spatial balance>"
    },
    "color_consistency": {
        "score": <0-100>,
        "feedback": "<brief feedback on color scheme and consistency>"
    },
    "typography": {
        "score": <0-100>,
        "feedback": "<brief feedback on fonts, sizes, hierarchy>"
    },
    "visual_appeal": {
        "score": <0-100>,
        "feedback": "<brief feedback on overall visual design quality>"
    },
    "design_strengths": ["<strength 1>", "<strength 2>"],
    "design_improvements": ["<improvement 1>", "<improvement 2>"],
    "design_summary": "<1-2 sentence summary of design quality>"
}
"""
        
        # Build messages with images for vision model
        messages = [
            {
                "role": "user",
                "content": []
            }
        ]
        
        # Add text prompt
        messages[0]["content"].append({
            "type": "text",
            "text": prompt_text
        })
        
        # Add images
        for idx, img_base64 in enumerate(slide_images_base64, 1):
            messages[0]["content"].append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_base64}"
                }
            })
        
        return prompt_text, messages
    
    def parse_design_evaluation_response(self, response_text: str) -> Dict:
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
            logger.error(f"Failed to parse JSON from design evaluation response: {e}")
            logger.debug(f"Response text: {response_text[:500]}")
            # Return error structure
            return {
                "error": "Failed to parse design evaluation response",
                "raw_response": response_text[:500]
            }
    
    def evaluate_design_from_metadata(self, design_description: str, filename: str, total_slides: int) -> Dict:
        """
        Evaluate design of PPT slides using design metadata (no PowerPoint required)
        design_description: Text description of design metadata extracted from PPTX
        """
        try:
            if not design_description or design_description.strip().startswith('['):
                # Check if it's an error message
                if design_description and design_description.strip().startswith('['):
                    return {
                        "error": design_description.strip('[]'),
                        "filename": filename
                    }
                return {
                    "error": "No design metadata provided for design evaluation",
                    "filename": filename
                }
            
            # Build prompt from metadata
            prompt_text = self.build_design_evaluation_prompt_from_metadata(
                design_description, filename, total_slides
            )
            
            # Call OpenRouter service with regular text model (no vision needed)
            result = self.openrouter_service.generate(
                prompt=prompt_text,
                system_message="You are an expert presentation design evaluator. Return ONLY valid JSON, no other text."
            )
            
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
            evaluation_result = self.parse_design_evaluation_response(response_text)
            
            # Add metadata
            evaluation_result['filename'] = filename
            evaluation_result['total_slides_analyzed'] = total_slides
            
            return evaluation_result
            
        except Exception as e:
            logger.error(f"Error evaluating PPT design from metadata: {e}", exc_info=True)
            return {
                "error": f"Error during design evaluation: {str(e)}",
                "filename": filename
            }
    
    def evaluate_design(self, slide_images_base64: List[str], filename: str) -> Dict:
        """
        Evaluate design of PPT slides using vision AI (legacy method - kept for backward compatibility)
        slide_images_base64: List of base64-encoded PNG images (one per slide)
        """
        try:
            if not slide_images_base64:
                return {
                    "error": "No slide images provided for design evaluation",
                    "filename": filename
                }
            
            # Build prompt with images
            prompt_text, messages = self.build_design_evaluation_prompt(slide_images_base64)
            
            # Call OpenRouter service with vision model
            # Use a vision-capable model (check if model supports vision)
            vision_model = self.openrouter_service.model
            # Common vision models: gpt-4-vision-preview, claude-3-opus, etc.
            # For now, try with the configured model - OpenRouter should handle vision if model supports it
            
            # Use the generate_with_images method if available, otherwise use generate
            result = self.openrouter_service.generate_with_images(
                messages=messages,
                model=vision_model
            )
            
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
            evaluation_result = self.parse_design_evaluation_response(response_text)
            
            # Add metadata
            evaluation_result['filename'] = filename
            evaluation_result['total_slides_analyzed'] = len(slide_images_base64)
            
            return evaluation_result
            
        except Exception as e:
            logger.error(f"Error evaluating PPT design: {e}", exc_info=True)
            return {
                "error": f"Error during design evaluation: {str(e)}",
                "filename": filename
            }
    
    def format_design_evaluation_result(self, evaluation_result: Dict) -> str:
        """
        Format design evaluation result as readable text
        """
        if "error" in evaluation_result:
            return f"Error: {evaluation_result.get('error', 'Unknown error')}"
        
        parts = []
        parts.append(f"File: {evaluation_result.get('filename', 'Unknown')}")
        parts.append(f"Slides Analyzed: {evaluation_result.get('total_slides_analyzed', 0)}")
        parts.append("")
        
        # Visual Clarity
        if "visual_clarity" in evaluation_result:
            vc = evaluation_result["visual_clarity"]
            parts.append(f"Visual Clarity Score: {vc.get('score', 'N/A')}/100")
            parts.append(f"Feedback: {vc.get('feedback', 'N/A')}")
            parts.append("")
        
        # Layout Balance
        if "layout_balance" in evaluation_result:
            lb = evaluation_result["layout_balance"]
            parts.append(f"Layout Balance Score: {lb.get('score', 'N/A')}/100")
            parts.append(f"Feedback: {lb.get('feedback', 'N/A')}")
            parts.append("")
        
        # Color Consistency
        if "color_consistency" in evaluation_result:
            cc = evaluation_result["color_consistency"]
            parts.append(f"Color Consistency Score: {cc.get('score', 'N/A')}/100")
            parts.append(f"Feedback: {cc.get('feedback', 'N/A')}")
            parts.append("")
        
        # Typography
        if "typography" in evaluation_result:
            typo = evaluation_result["typography"]
            parts.append(f"Typography Score: {typo.get('score', 'N/A')}/100")
            parts.append(f"Feedback: {typo.get('feedback', 'N/A')}")
            parts.append("")
        
        # Visual Appeal
        if "visual_appeal" in evaluation_result:
            va = evaluation_result["visual_appeal"]
            parts.append(f"Visual Appeal Score: {va.get('score', 'N/A')}/100")
            parts.append(f"Feedback: {va.get('feedback', 'N/A')}")
            parts.append("")
        
        # Design Strengths
        if "design_strengths" in evaluation_result:
            parts.append("Design Strengths:")
            for strength in evaluation_result["design_strengths"]:
                parts.append(f"  - {strength}")
            parts.append("")
        
        # Design Improvements
        if "design_improvements" in evaluation_result:
            parts.append("Design Improvements:")
            for improvement in evaluation_result["design_improvements"]:
                parts.append(f"  - {improvement}")
            parts.append("")
        
        # Design Summary
        if "design_summary" in evaluation_result:
            parts.append(f"Design Summary: {evaluation_result['design_summary']}")
        
        return "\n".join(parts)

