from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import json
import re
import os
import uuid
from pathlib import Path
from dotenv import load_dotenv

from .database import SessionLocal, engine, Base
from .models import User
from .auth import verify_password, get_password_hash, create_access_token, get_current_user
from .file_processor import FileProcessor
from .openrouter_service import OpenRouterService
from .github_service import GitHubService
from .git_evaluator import GitEvaluator
from .ppt_processor import PPTProcessor
from .ppt_evaluator import PPTEvaluator
from .ppt_design_evaluator import PPTDesignEvaluator

load_dotenv()

# Configure logging early so debug/info messages are visible during request handling
import logging
logging.basicConfig(level=(os.getenv('APP_LOG_LEVEL','INFO')))
logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

# Create uploads directory for temporary file storage
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Initialize services
file_processor = FileProcessor()
openrouter_service = OpenRouterService()
github_service = GitHubService()
git_evaluator = GitEvaluator(openrouter_service)
ppt_evaluator = PPTEvaluator(openrouter_service)
ppt_design_evaluator = PPTDesignEvaluator(openrouter_service)

app = FastAPI(title="Login API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Pydantic models
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    token: str
    user: UserResponse


class RegisterResponse(BaseModel):
    message: str
    user: UserResponse


class GenerateRequest(BaseModel):
    title: str
    description: str
    file_ids: List[str]
    github_url: Optional[str] = None
    evaluate_design: Optional[bool] = False  # If True, evaluate visual design instead of content


class GenerateResponse(BaseModel):
    success: bool
    result: str
    summary: Optional[str] = None
    scores: Optional[List[dict]] = None
    error: Optional[str] = None


class GitEvaluateRequest(BaseModel):
    github_url: str


class GitEvaluateResponse(BaseModel):
    success: bool
    result: Optional[dict] = None
    error: Optional[str] = None
    raw_response: Optional[str] = None


class GitGradeRequest(BaseModel):
    github_url: str
    description: str


class GitGradeResponse(BaseModel):
    success: bool
    result: Optional[dict] = None
    error: Optional[str] = None
    raw_response: Optional[str] = None


@app.get("/")
def read_root():
    return {"message": "Welcome to Login API"}


@app.post("/register", response_model=RegisterResponse)
def register(register_data: RegisterRequest, db: Session = Depends(get_db)):
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == register_data.email).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Validate password length
    if len(register_data.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long"
        )
    
    # Create new user
    hashed_password = get_password_hash(register_data.password)
    new_user = User(
        email=register_data.email,
        hashed_password=hashed_password
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {
        "message": "User registered successfully",
        "user": UserResponse(id=new_user.id, email=new_user.email)
    }


@app.post("/login", response_model=LoginResponse)
def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    # Find user by email
    user = db.query(User).filter(User.email == login_data.email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Verify password
    if not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Create access token
    access_token = create_access_token(data={"sub": user.email})
    
    return {
        "token": access_token,
        "user": UserResponse(id=user.id, email=user.email)
    }


@app.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    return UserResponse(id=current_user.id, email=current_user.email)


@app.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Upload multiple files temporarily
    Files are stored until generate is called
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 files allowed")
    
    file_ids = []
    saved_files = {}
    
    try:
        for file in files:
            # Generate unique file ID
            file_id = str(uuid.uuid4())
            
            # Validate file size (max 10MB per file)
            file_content = await file.read()
            if len(file_content) > 10 * 1024 * 1024:  # 10MB
                raise HTTPException(
                    status_code=400,
                    detail=f"File {file.filename} exceeds 10MB limit"
                )
            
            # Save file temporarily
            file_extension = Path(file.filename).suffix
            saved_filename = f"{file_id}{file_extension}"
            file_path = UPLOAD_DIR / saved_filename
            
            with open(file_path, "wb") as buffer:
                buffer.write(file_content)
            # Save original filename metadata
            try:
                meta_path = UPLOAD_DIR / f"{file_id}.meta.json"
                with open(meta_path, "w", encoding="utf-8") as m:
                    json.dump({"original_filename": file.filename}, m)
            except Exception:
                pass
            
            file_ids.append(file_id)
            saved_files[file_id] = {
                "filename": file.filename,
                "path": str(file_path),
                "size": len(file_content)
            }
        
        return {
            "success": True,
            "file_ids": file_ids,
            "files": saved_files,
            "message": f"Successfully uploaded {len(files)} file(s)"
        }
    
    except HTTPException:
        # Clean up on error
        for file_id, file_info in saved_files.items():
            file_path = Path(file_info["path"])
            if file_path.exists():
                file_path.unlink()
        raise
    except Exception as e:
        # Clean up on error
        for file_id, file_info in saved_files.items():
            file_path = Path(file_info["path"])
            if file_path.exists():
                file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Error uploading files: {str(e)}")


@app.post("/generate", response_model=GenerateResponse)
async def generate_content(
    request: GenerateRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Generate content using Ollama based on description and uploaded files
    """
    if not request.description.strip():
        raise HTTPException(status_code=400, detail="Description is required")
    
    # Check for GitHub URL
    github_url = request.github_url or None
    if not github_url:
        # Fallback: check description for GitHub URL
        desc_lower = (request.description or "").lower()
        if "github.com" in desc_lower:
            # Try to extract GitHub URL from description
            import re
            github_match = re.search(r'https?://github\.com/[\w\-\.]+/[\w\-\.]+', request.description)
            if github_match:
                github_url = github_match.group(0)
    
    # Require at least one file or GitHub URL
    if not request.file_ids and not github_url:
        raise HTTPException(status_code=400, detail="Provide at least one file or a valid GitHub repository URL")
    
    try:
        # Read all files
        file_contents = []
        file_paths_to_cleanup = []
        meta_paths_to_cleanup = []
        file_basenames = []
        
        # Fetch GitHub repository files if URL is provided
        if github_url:
            logger.info(f"Fetching files from GitHub repository: {github_url}")
            try:
                github_files = github_service.fetch_repository_files(github_url, max_files=100)
                logger.info(f"Fetched {len(github_files)} files from GitHub")
                
                # Process each GitHub file
                for gh_file in github_files:
                    file_path_obj = Path(gh_file['path'])
                    file_ext = file_path_obj.suffix.lower()
                    
                    # Create file data from GitHub file content
                    file_data = {
                        'filename': gh_file['name'],
                        'content': gh_file['content'],
                        'file_type': 'github',
                        'extension': file_ext,
                        'path': gh_file['path']
                    }
                    
                    # Determine file type based on extension
                    if file_ext in file_processor.TEXT_EXTENSIONS:
                        file_data['file_type'] = 'text'
                    elif file_ext == '.json':
                        file_data['file_type'] = 'json'
                    elif file_ext in ['.xlsx', '.xls']:
                        file_data['file_type'] = 'excel'
                    elif file_ext == '.csv':
                        file_data['file_type'] = 'csv'
                    
                    file_contents.append(file_data)
                    file_basenames.append(file_path_obj.stem)
                    logger.debug(f"Added GitHub file: {gh_file['path']}")
                
            except Exception as e:
                logger.error(f"Error fetching GitHub files: {e}")
                # Continue even if GitHub fetch fails
                pass
        
        # Process uploaded files
        for file_id in request.file_ids:
            # Find the file
            file_path = None
            original_filename = None
            
            # Search for the actual uploaded file (exclude sidecar metadata)
            for saved_file in UPLOAD_DIR.glob(f"{file_id}.*"):
                # Skip metadata file
                if saved_file.name == f"{file_id}.meta.json":
                    continue
                file_path = saved_file
                # Fallback original filename to saved name until we read metadata
                original_filename = saved_file.name
                break
            
            if not file_path or not file_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"File with ID {file_id} not found"
                )
            
            # Try to read metadata for original filename
            try:
                meta_path = UPLOAD_DIR / f"{file_id}.meta.json"
                if meta_path.exists():
                    with open(meta_path, "r", encoding="utf-8") as m:
                        md = json.load(m)
                        if isinstance(md, dict):
                            original_filename = md.get("original_filename") or original_filename
                meta_paths_to_cleanup.append(meta_path)
            except Exception:
                pass

            # Read file content - wrap in try/except to ensure processing continues even if one file fails
            try:
                file_data = file_processor.read_file(str(file_path))
            except Exception as e:
                # If file reading fails completely, create a minimal file_data entry
                file_data = {
                    'filename': original_filename or file_path.name,
                    'content': f"[Error reading file: {str(e)}]",
                    'file_type': 'error',
                    'extension': Path(file_path).suffix.lower()
                }

            # If extractor returned no text or placeholder, try a forced OCR pass (NVIDIA or tesseract)
            content_preview = (file_data.get('content') or '').strip()
            placeholder_indicators = [
                '[No extractable text',
                '[No text extracted',
                '[Error reading DOCX',
                '[Cannot read .doc',
                '[Error reading DOC',
                '[No extractable text found in PDF',
                '[Error reading file:',
                '[Error reading DOC via COM',
            ]
            try:
                # Check if content is an error message or too short
                is_error_message = any(ind in content_preview for ind in placeholder_indicators)
                is_too_short = len(content_preview) < 32
                file_ext = Path(file_path).suffix.lower()
                
                if (not content_preview) or is_error_message or (is_too_short and file_ext == '.doc'):
                    # For DOC files, always try OCR if initial extraction failed
                    if file_ext == '.doc':
                        logger.info(f"Attempting OCR for DOC file: {file_path.name}")
                        ocr_text = file_processor.force_ocr(str(file_path))
                        if ocr_text and isinstance(ocr_text, str) and ocr_text.strip():
                            # Verify OCR result is not an error message
                            if not any(ind in ocr_text for ind in placeholder_indicators):
                                file_data['content'] = ocr_text
                                file_data['file_type'] = file_data.get('file_type') or 'ocr'
                                file_data['from_ocr'] = True
                                logger.info(f"Successfully extracted content via OCR for {file_path.name} ({len(ocr_text)} chars)")
                            else:
                                logger.warning(f"OCR returned error message for {file_path.name}")
                        else:
                            logger.warning(f"OCR failed or returned empty for {file_path.name}")
                    else:
                        # For other file types, try OCR
                        ocr_text = file_processor.force_ocr(str(file_path))
                        if ocr_text and isinstance(ocr_text, str) and ocr_text.strip():
                            if not any(ind in ocr_text for ind in placeholder_indicators):
                                file_data['content'] = ocr_text
                                file_data['file_type'] = file_data.get('file_type') or 'ocr'
                                file_data['from_ocr'] = True
            except Exception as e:
                # Log the error but continue processing
                logger.warning(f"OCR fallback failed for {file_path}: {e}", exc_info=True)
                pass

            file_contents.append(file_data)
            file_paths_to_cleanup.append(file_path)
            try:
                # Prefer original filename from metadata; fall back to processor or saved name
                original_name = original_filename or file_data.get("filename") or file_path.name
                file_basenames.append(Path(original_name).stem)
            except Exception:
                file_basenames.append(Path(file_path.name).stem)
        
        # Check if all files are PPT files - if so, use PPT evaluator
        all_ppt_files = all(
            fd.get('file_type') == 'ppt' or 
            Path(fd.get('filename', '')).suffix.lower() in ['.ppt', '.pptx', '.pptm']
            for fd in file_contents
        )
        
        if all_ppt_files and len(file_contents) > 0:
            # Check if design evaluation is requested
            evaluate_design = request.evaluate_design or False
            
            if evaluate_design:
                # Evaluate BOTH content and visual design when checkbox is checked
                logger.info(f"Detected {len(file_contents)} PPT file(s), evaluating both content and visual design")
                try:
                    formatted_results = []
                    file_idx = 0
                    for file_id in request.file_ids:
                        # Find the file path and original filename
                        file_path = None
                        original_filename = None
                        
                        # First, try to get original filename from metadata
                        try:
                            meta_path = UPLOAD_DIR / f"{file_id}.meta.json"
                            if meta_path.exists():
                                with open(meta_path, "r", encoding="utf-8") as m:
                                    md = json.load(m)
                                    if isinstance(md, dict):
                                        original_filename = md.get("original_filename")
                        except Exception:
                            pass
                        
                        # Find the actual file
                        for saved_file in UPLOAD_DIR.glob(f"{file_id}.*"):
                            if saved_file.name == f"{file_id}.meta.json":
                                continue
                            file_path = saved_file
                            break
                        
                        if file_path and file_path.exists() and file_idx < len(file_contents):
                            # Use original filename from metadata, fallback to file_contents, then file path name
                            filename = original_filename or file_contents[file_idx].get('filename') or file_path.name
                            logger.info(f"Processing PPT file for combined evaluation: {file_path} (original: {filename})")
                            
                            try:
                                # Step 1: Extract text content for content evaluation
                                ppt_result = PPTProcessor.process_ppt_file(str(file_path))
                                ppt_result['filename'] = filename
                                
                                # Step 2: Extract design metadata for design evaluation
                                design_metadata = PPTProcessor.extract_design_metadata(str(file_path))
                                design_description = design_metadata.get('design_description', '')
                                total_slides = design_metadata.get('total_slides', 0) or ppt_result.get('total_slides', 0)
                                
                                # Initialize result parts
                                result_parts = []
                                result_parts.append(f"File: {filename}")
                                result_parts.append(f"Total Slides: {total_slides}")
                                result_parts.append("")
                                result_parts.append("=" * 60)
                                result_parts.append("CONTENT EVALUATION")
                                result_parts.append("=" * 60)
                                result_parts.append("")
                                
                                # Evaluate content
                                content_error = False
                                if not ppt_result.get('slides_text') or ppt_result.get('slides_text', '').strip().startswith('['):
                                    error_msg = ppt_result.get('slides_text', 'Could not extract text content').strip('[]')
                                    result_parts.append(f"Error: {error_msg}")
                                    content_error = True
                                else:
                                    content_result = ppt_evaluator.evaluate_ppt(
                                        request.title,
                                        request.description,
                                        ppt_result
                                    )
                                    
                                    if 'error' in content_result:
                                        result_parts.append(f"Error: {content_result.get('error')}")
                                        content_error = True
                                    else:
                                        result_parts.append(ppt_evaluator.format_evaluation_result(content_result))
                                
                                # Add design evaluation section
                                result_parts.append("")
                                result_parts.append("=" * 60)
                                result_parts.append("VISUAL DESIGN EVALUATION")
                                result_parts.append("=" * 60)
                                result_parts.append("")
                                
                                # Evaluate design
                                design_error = False
                                design_result = None
                                if not design_description or design_description.strip().startswith('['):
                                    error_msg = design_description.strip('[]') if design_description.strip().startswith('[') else "Could not extract design metadata"
                                    result_parts.append(f"Error: {error_msg}")
                                    design_error = True
                                else:
                                    design_result = ppt_design_evaluator.evaluate_design_from_metadata(
                                        design_description,
                                        filename,
                                        total_slides
                                    )
                                    
                                    if 'error' in design_result:
                                        result_parts.append(f"Error: {design_result.get('error')}")
                                        design_error = True
                                    else:
                                        result_parts.append(ppt_design_evaluator.format_design_evaluation_result(design_result))
                                
                                # Add overall summary if both evaluations succeeded
                                if not content_error and not design_error:
                                    result_parts.append("")
                                    result_parts.append("=" * 60)
                                    result_parts.append("OVERALL SUMMARY")
                                    result_parts.append("=" * 60)
                                    result_parts.append("")
                                    result_parts.append("This presentation has been evaluated for both content quality and visual design.")
                                    result_parts.append("Review the sections above for detailed feedback on each aspect.")
                                
                                formatted_results.append("\n".join(result_parts))
                                
                            except Exception as e:
                                logger.error(f"Exception during combined evaluation for {filename}: {e}", exc_info=True)
                                formatted_results.append(f"Error for {filename}: Exception during evaluation - {str(e)}")
                        else:
                            # Try to get original filename from metadata even if file not found
                            original_filename = None
                            try:
                                meta_path = UPLOAD_DIR / f"{file_id}.meta.json"
                                if meta_path.exists():
                                    with open(meta_path, "r", encoding="utf-8") as m:
                                        md = json.load(m)
                                        if isinstance(md, dict):
                                            original_filename = md.get("original_filename")
                            except Exception:
                                pass
                            
                            filename = original_filename or (file_contents[file_idx].get('filename', 'Unknown') if file_idx < len(file_contents) else 'Unknown')
                            formatted_results.append(f"Error for {filename}: File not found")
                        
                        file_idx += 1
                    
                    result_text = "\n\n".join(formatted_results)
                    
                except Exception as e:
                    logger.error(f"Error in combined PPT evaluation: {e}", exc_info=True)
                    result_text = f"Error during evaluation: {str(e)}"
            else:
                # Use PPT content evaluator (text content analysis)
                logger.info(f"Detected {len(file_contents)} PPT file(s), using PPT content evaluator")
                try:
                    ppt_files_data = []
                    file_idx = 0
                    for file_id in request.file_ids:
                        # Find the file path and original filename
                        file_path = None
                        original_filename = None
                        
                        # First, try to get original filename from metadata
                        try:
                            meta_path = UPLOAD_DIR / f"{file_id}.meta.json"
                            if meta_path.exists():
                                with open(meta_path, "r", encoding="utf-8") as m:
                                    md = json.load(m)
                                    if isinstance(md, dict):
                                        original_filename = md.get("original_filename")
                        except Exception:
                            pass
                        
                        # Find the actual file
                        for saved_file in UPLOAD_DIR.glob(f"{file_id}.*"):
                            if saved_file.name == f"{file_id}.meta.json":
                                continue
                            file_path = saved_file
                            break
                        
                        if file_path and file_path.exists() and file_idx < len(file_contents):
                            # Use original filename from metadata, fallback to file_contents, then file path name
                            filename = original_filename or file_contents[file_idx].get('filename') or file_path.name
                            logger.info(f"Processing PPT file: {file_path} (original: {filename})")
                            ppt_result = PPTProcessor.process_ppt_file(str(file_path))
                            ppt_result['filename'] = filename
                            logger.info(f"PPT extraction result for {ppt_result['filename']}: total_slides={ppt_result.get('total_slides', 0)}, slides_text_length={len(ppt_result.get('slides_text', ''))}")
                            ppt_files_data.append(ppt_result)
                        elif file_idx < len(file_contents):
                            # Fallback: use content from file_data
                            ppt_files_data.append({
                                'filename': file_contents[file_idx].get('filename', 'Unknown'),
                                'slides_text': file_contents[file_idx].get('content', ''),
                                'total_slides': 0,
                                'slide_details': []
                            })
                        file_idx += 1
                    
                    # Evaluate PPT files
                    evaluation_result = ppt_evaluator.evaluate_multiple_ppts(
                        request.title,
                        request.description,
                        ppt_files_data
                    )
                    
                    # Format results
                    formatted_results = []
                    for eval_data in evaluation_result.get('evaluations', []):
                        if 'error' in eval_data:
                            formatted_results.append(f"Error for {eval_data.get('filename', 'Unknown')}: {eval_data.get('error')}")
                        else:
                            formatted_results.append(ppt_evaluator.format_evaluation_result(eval_data))
                    
                    result_text = "\n\n".join(formatted_results)
                    
                except Exception as e:
                    logger.error(f"Error in PPT content evaluation: {e}", exc_info=True)
                    result_text = f"Error during content evaluation: {str(e)}"
            
            # Clean up files (for both design and content evaluation)
            try:
                for file_path in file_paths_to_cleanup:
                    try:
                        if file_path.exists():
                            file_path.unlink()
                    except Exception:
                        pass
                for meta_path in meta_paths_to_cleanup:
                    try:
                        if meta_path.exists():
                            meta_path.unlink()
                    except Exception:
                        pass
                
                return {
                    "success": True,
                    "result": result_text,
                    "summary": None,
                    "scores": []
                }
                
            except Exception as e:
                logger.error(f"Error in PPT evaluation: {e}", exc_info=True)
                # Fall through to regular processing if PPT evaluation fails
                pass
        
        # Helper: detect if extracted content contains question-like patterns
        def detect_question_like(text: str) -> bool:
            if not text or not isinstance(text, str):
                return False
            patterns = [
                r"\bQ(?:uestion)?\s*\d+\b",
                r"\bQ\d+\b",
                r"\bQuestion:\b",
                r"\bName:\b",
                r"\bStudent:\b",
                r"\bCandidate:\b",
                r"^\d+\.\s",
            ]
            for p in patterns:
                try:
                    if re.search(p, text, flags=re.IGNORECASE | re.MULTILINE):
                        return True
                except Exception:
                    continue
            return False

        # Build batched prompts to ensure all files are processed
        def build_prompt(intro_title: str, intro_desc: str, files_subset):
            # Compute base names for explicit naming
            subset_names = []
            try:
                for _fd in files_subset:
                    try:
                        subset_names.append(_fd.get('display_name') or Path(_fd.get('filename', '')).stem or 'Unnamed')
                    except Exception:
                        subset_names.append('Unnamed')
            except Exception:
                subset_names = []
            parts = [
                f"Title: {intro_title}\n",
                f"Task Description (General Instructions Only):\n{intro_desc}\n\n",
                "You are a strict grader. You will be given ONLY the extracted TEXT CONTENT from uploaded files (PDF, DOCX, XLSX, TXT, etc.).\n",
                "\n",
                "Important constraints:\n",
                "- The uploaded file text may contain MULTIPLE students.\n",
                "- Each student MAY have a DIFFERENT SET OF QUESTIONS and DIFFERENT ANSWERS.\n",
                "- Questions are present inside the uploaded file text and may vary per student.\n",
                "- For EACH student:\n",
                "  - Identify the student name using patterns like 'Name:', 'Student:', 'Candidate:'.\n",
                "  - Extract ONLY the questions that belong to that specific student.\n",
                "  - Extract the corresponding answers provided by that student.\n",
                "- Do NOT assume that questions are shared across students.\n",
                "\n",
                "Grading rules:\n",
                "- If an Answer Key or Rubric is present anywhere in the file text, apply it to the relevant questions.\n",
                "- If no Answer Key is found, infer correct answers based on the question and standard academic expectations.\n",
                "- Evaluate each student STRICTLY based on THEIR OWN questions and answers only.\n",
                "- Compute an OVERALL percentage score (score_percent) between 0-100 (round to one decimal if needed).\n",
                "- Provide concise reasoning explaining which answers were correct or incorrect for that student.\n",
                "- If any questions, answers, or mappings are missing or ambiguous, be conservative and explicitly state assumptions.\n",
                "\n",
                "Output requirements:\n",
                "- Treat EACH FILE as ONE distinct student's submission; do NOT merge content across files.\n",
                "- Produce EXACTLY one entry per file, in the SAME ORDER as files appear below.\n",
                ("- Use these exact names for the 'name' field, in order: " + ", ".join(subset_names) + "\n") if subset_names else "",
                "- For EACH student's questions, return granular 'details' entries for each question you identified.\n",
                "- For each detail include: the question (or a concise label if long), the student's answer (if present), the correct answer (from key or inferred), whether it is correct, and a short feedback.\n",
                "- Compute score_percent from the proportion of correct details (0-100).\n",
                "Return ONLY JSON (no prose, no markdown) in this exact schema:\n",
                "{\n  \"summary\": string,\n  \"scores\": [\n    {\n      \"name\": string,\n      \"score_percent\": number,\n      \"reasoning\": string,\n      \"details\": [\n        {\n          \"question\": string,\n          \"student_answer\": string,\n          \"correct_answer\": string,\n          \"is_correct\": boolean,\n          \"feedback\": string\n        }\n      ]\n    }\n  ]\n}\n",
                "\nHere are the files (extracted text follows):\n\n",



            ]
            for fd in files_subset:
                parts.append(f"--- File: {fd['filename']} ({fd['file_type']}) ---\n")
                
                # If this is an error message, tell the model explicitly
                if fd.get('is_error', False):
                    parts.append("[WARNING: This file could not be processed. The content below is an error message, not actual file content. Return score_percent: 0.00 and reasoning explaining that the file could not be read.]\n")
                
                # If the extractor did not detect questions, include an explicit hint for the model
                if not fd.get('has_questions', True) and not fd.get('is_error', False):
                    parts.append("[NOTE: This file may contain questions/answers in tables, headers, or non-standard formats — search thoroughly.]\n")

                # If we extracted QA pairs, include them explicitly to help the model
                try:
                    qa = fd.get('qa_pairs') or []
                    if qa:
                        parts.append("EXTRACTED_QUESTION_ANSWER_PAIRS:\n")
                        for p in qa:
                            qtxt = p.get('question') or ''
                            atxt = p.get('answer') or '[NO ANSWER EXTRACTED]'
                            parts.append(f"Q: {qtxt}\nA: {atxt}\n\n")
                except Exception:
                    pass

                parts.append(fd['content_processed'])
                parts.append("\n\n")
            return "".join(parts)

        # Log prepared file summaries (length and whether they appear to contain questions)
        try:
            for fd in prepared:
                content_snippet = (fd.get('content', '') or '')[:200].replace('\n', ' ')
                logger.debug(f"Prepared file='{fd.get('filename')}' type={fd.get('file_type')} len={len(fd.get('content',''))} has_questions={fd.get('has_questions')} snippet='{content_snippet}'")
        except Exception:
            pass

        # Limits (reuse existing env names for compatibility)
        per_file_limit = int(os.getenv("OLLAMA_PER_FILE_CHAR_LIMIT", "20000"))
        total_limit = int(os.getenv("OLLAMA_TOTAL_CHAR_LIMIT", "60000"))

        # Helper: extract simple QA pairs from extracted content
        def extract_qa_pairs(text: str):
            qa = []
            if not text or not isinstance(text, str):
                return qa
            lines = [l.rstrip() for l in text.splitlines()]
            i = 0
            question_re = re.compile(r"^\s*(?:Question\b[:\s]*|Q\d*[:\s]*|Q\d+\b|\d+\s*[\.)\-:])", flags=re.IGNORECASE)
            answer_marker_re = re.compile(r"\bAnswer\b[:\s]*", flags=re.IGNORECASE)

            while i < len(lines):
                line = lines[i].strip()
                if not line:
                    i += 1
                    continue
                # Table-like row with tabs
                if '\t' in line:
                    cells = [c.strip() for c in line.split('\t')]
                    lc = [c.lower() for c in cells]
                    # try to find 'question' and 'answer' cells
                    if any('question' in c for c in lc) or any('answer' in c for c in lc) or any('q' == c for c in lc):
                        # naive mapping: question = first cell, answer = last cell
                        q = cells[0]
                        a = cells[1] if len(cells) > 1 else ''
                        qa.append({'question': q, 'answer': a})
                        i += 1
                        continue
                # line contains explicit Question keyword or numbered question
                if question_re.search(line) or '?' in line:
                    # extract question text
                    qtext = re.sub(r"^\s*(?:Question\b[:\s]*|Q\d*[:\s]*|\d+\s*[\.)\-:]\s*)", '', line, flags=re.IGNORECASE)
                    # collect following lines as answer until next question or blank separator
                    ans_lines = []
                    j = i + 1
                    while j < len(lines):
                        l = lines[j].strip()
                        if not l:
                            # allow short blank separators
                            j += 1
                            # but break if next non-empty line looks like a question
                            if j < len(lines) and question_re.search(lines[j]):
                                break
                            continue
                        if question_re.search(l):
                            break
                        # If this line has 'Answer:' marker, strip it and include
                        if answer_marker_re.search(l):
                            a = answer_marker_re.sub('', l).strip()
                            if a:
                                ans_lines.append(a)
                            j += 1
                            # collect subsequent non-question lines
                            while j < len(lines) and not question_re.search(lines[j]):
                                if lines[j].strip():
                                    ans_lines.append(lines[j].strip())
                                j += 1
                            break
                        ans_lines.append(l)
                        j += 1
                    answer = ' '.join(ans_lines).strip()
                    qa.append({'question': qtext.strip() or line, 'answer': answer or None})
                    i = j
                    continue
                i += 1
            return qa

        # Preprocess content with per-file truncation and QA extraction
        prepared = []
        error_message_indicators = [
            '[No extractable text',
            '[No text extracted',
            '[Error reading DOCX',
            '[Cannot read .doc',
            '[Error reading DOC',
            '[No extractable text found in PDF',
            '[Error reading file:',
            '[Error reading DOC via COM',
            '[python-docx library not available]',
            '[PDF library not available',
            '[Excel library not available',
            '[Binary file -',
        ]
        
        for idx, fd in enumerate(file_contents):
            content = fd.get('content', '')
            if not isinstance(content, str):
                content = str(content)
            
            # Check if content is an error message
            is_error_message = any(ind in content for ind in error_message_indicators)
            
            if not content.strip() or is_error_message:
                # If it's an error message or empty, mark it as such
                if is_error_message:
                    content = f"[ERROR: Could not extract content from {fd.get('filename', 'file')}. The file may be corrupted, password-protected, or in an unsupported format.]"
                else:
                    content = "[No extractable text from file]"
            
            truncated_note = ""
            if len(content) > per_file_limit:
                overflow = len(content) - per_file_limit
                content = content[:per_file_limit]
                truncated_note = f"\n[TRUNCATED {overflow} chars due to per-file limit]"
            fd_copy = dict(fd)
            fd_copy['content_processed'] = f"{content}{truncated_note}"
            fd_copy['is_error'] = is_error_message
            # Carry a stable display name aligned with original filenames
            try:
                if idx < len(file_basenames):
                    fd_copy['display_name'] = file_basenames[idx]
                else:
                    fd_copy['display_name'] = Path(fd.get('filename', '')).stem or 'Unnamed'
            except Exception:
                fd_copy['display_name'] = Path(fd.get('filename', '')).stem or 'Unnamed'

            # Detect and extract QA pairs
            try:
                qa_pairs = extract_qa_pairs(content)
                fd_copy['qa_pairs'] = qa_pairs
                fd_copy['has_questions'] = bool(qa_pairs) or detect_question_like(content)
            except Exception:
                fd_copy['qa_pairs'] = []
                fd_copy['has_questions'] = detect_question_like(content)

            prepared.append(fd_copy)

        # Log prepared file summaries for debugging (filename, type, content length and whether it appears to contain Q/A)
        try:
            for i, fd in enumerate(prepared):
                snippet = (fd.get('content_processed') or '')[:250].replace('\n', ' ')
                logger.info(f"Prepared file idx={i} name={fd.get('filename')} type={fd.get('file_type')} len={len(fd.get('content_processed',''))} has_questions={fd.get('has_questions')} snippet='{snippet}'")
        except Exception:
            pass

        # Create batches under total_limit
        batches = []
        current_batch = []
        current_size = 0
        for fd in prepared:
            c = fd['content_processed']
            # Approximate size impact: content length only (headers are small)
            if current_size == 0:
                current_batch.append(fd)
                current_size += len(c)
            else:
                if current_size + len(c) > total_limit:
                    batches.append(current_batch)
                    current_batch = [fd]
                    current_size = len(c)
                else:
                    current_batch.append(fd)
                    current_size += len(c)
        if current_batch:
            batches.append(current_batch)

        # Aggregate results across batches
        agg_scores = []
        agg_summary_parts = []
        raw_concat = []

        for batch in batches:
            prompt = build_prompt(request.title, request.description, batch)
            result = openrouter_service.generate(prompt)
            if not result.get("success"):
                continue
            raw = result.get("response", "")
            raw_concat.append(raw)
            b_summary = None
            b_scores = None
            try:
                data = json.loads(raw)
                b_summary = data.get("summary")
                b_scores = data.get("scores")
            except Exception:
                try:
                    match = re.search(r"\{[\s\S]*\}", raw)
                    if match:
                        data = json.loads(match.group(0))
                        b_summary = data.get("summary")
                        b_scores = data.get("scores")
                except Exception:
                    pass

            # Map names for this batch using the corresponding basenames by index
            try:
                if isinstance(b_scores, list) and b_scores:
                    # Use display_name carried into batch items
                    batch_basenames = [fd.get('display_name') for fd in batch]

                    if len(batch_basenames) == 1:
                        base = batch_basenames[0] or "Unnamed"
                        for s in b_scores:
                            if isinstance(s, dict):
                                s["name"] = base
                    elif len(b_scores) == len(batch_basenames):
                        for i, s in enumerate(b_scores):
                            if isinstance(s, dict) and batch_basenames[i]:
                                s["name"] = batch_basenames[i]
                    else:
                        m = min(len(b_scores), len(batch_basenames))
                        for i in range(m):
                            s = b_scores[i]
                            if isinstance(s, dict) and batch_basenames[i]:
                                s["name"] = batch_basenames[i]
            except Exception:
                pass

            if isinstance(b_scores, list):
                agg_scores.extend(b_scores)
            if b_summary:
                agg_summary_parts.append(b_summary)

        combined_summary = "\n---\n".join(agg_summary_parts) if agg_summary_parts else None
        combined_raw = "\n\n".join(raw_concat)

        # Ensure one score/result per uploaded file (preserve original order)
        try:
            final_scores = []
            used_indices = set()
            for idx, base in enumerate(file_basenames):
                assigned = None
                # First try exact name match against returned scores
                for j, s in enumerate(agg_scores):
                    if j in used_indices or not isinstance(s, dict):
                        continue
                    name = s.get('name') or ''
                    if name and name == base:
                        assigned = (j, s)
                        break
                # Then try case-insensitive match
                if not assigned:
                    for j, s in enumerate(agg_scores):
                        if j in used_indices or not isinstance(s, dict):
                            continue
                        name = s.get('name') or ''
                        if name and name.lower() == str(base).lower():
                            assigned = (j, s)
                            break
                # Fallback: take the score at the same index if available and unused
                if not assigned and idx < len(agg_scores) and idx not in used_indices:
                    assigned = (idx, agg_scores[idx])
                if assigned:
                    j, s = assigned
                    used_indices.add(j)
                    final_scores.append(s)
                else:
                    # Check if this file had an error during extraction
                    file_has_error = False
                    try:
                        if idx < len(prepared):
                            file_has_error = prepared[idx].get('is_error', False)
                    except Exception:
                        pass
                    
                    # Placeholder for missing result
                    if file_has_error:
                        final_scores.append({
                            'name': base or f'File {idx+1}',
                            'score_percent': 0.0,
                            'reasoning': 'No content was found within the document to evaluate. The file could not be processed (may be corrupted, password-protected, or in an unsupported format).',
                            'details': []
                        })
                    else:
                        final_scores.append({
                            'name': base or f'File {idx+1}',
                            'score_percent': None,
                            'reasoning': 'No result returned by model for this file (possibly truncated/prompt overflow or model error).',
                            'details': []
                        })
            # Ensure lengths match exactly
            while len(final_scores) < len(file_basenames):
                i = len(final_scores)
                # Check if this file had an error during extraction
                file_has_error = False
                try:
                    if i < len(prepared):
                        file_has_error = prepared[i].get('is_error', False)
                except Exception:
                    pass
                
                if file_has_error:
                    final_scores.append({
                        'name': file_basenames[i] if i < len(file_basenames) else f'File {i+1}',
                        'score_percent': 0.0,
                        'reasoning': 'No content was found within the document to evaluate. The file could not be processed.',
                        'details': []
                    })
                else:
                    final_scores.append({
                        'name': file_basenames[i] if i < len(file_basenames) else f'File {i+1}',
                        'score_percent': None,
                        'reasoning': 'No result returned by model for this file.',
                        'details': []
                    })
            # Replace aggregated scores with final aligned list
            agg_scores = final_scores

            # Log missing placeholders for observability
            missing_count = sum(1 for s in agg_scores if s.get('score_percent') is None)
            if missing_count:
                logger.warning(f"{missing_count} file(s) had no model results; placeholders were added.")

                # Attempt per-file retry for missing results: query the model with a simplified prompt for each missing file
                try:
                    for i, s in enumerate(final_scores):
                        if s.get('score_percent') is not None:
                            continue
                        # Get the corresponding prepared file if available
                        try:
                            fd = prepared[i]
                        except Exception:
                            fd = None

                        if not fd:
                            continue

                        single_title = request.title or "Grading Task"
                        single_desc = (request.description or "").strip()

                        simple_parts = [
                            f"Title: {single_title}\n",
                            "You are a strict grader. Return ONLY JSON in the exact schema specified below. Be concise and conservative when assumptions are needed.\n",
                            "Schema:\n{ \"summary\": string, \"scores\": [{ \"name\": string, \"score_percent\": number, \"reasoning\": string, \"details\": [] }] }\n",
                            f"--- File: {fd.get('filename')} ({fd.get('file_type')}) ---\n",
                            fd.get('content_processed') or fd.get('content') or "[No content]",
                        ]
                        simple_prompt = "\n".join(simple_parts)

                        retry_resp = openrouter_service.generate(simple_prompt)
                        if not retry_resp.get('success'):
                            logger.debug(f"Retry for file {fd.get('filename')} failed: {retry_resp.get('error')}")
                            continue
                        raw_retry = retry_resp.get('response', '')
                        # Try to parse JSON from response
                        parsed = None
                        try:
                            parsed = json.loads(raw_retry)
                        except Exception:
                            try:
                                m = re.search(r"\{[\s\S]*\}", raw_retry)
                                if m:
                                    parsed = json.loads(m.group(0))
                            except Exception:
                                parsed = None

                        if parsed and isinstance(parsed, dict):
                            scores_list = parsed.get('scores') or []
                            if isinstance(scores_list, list) and scores_list:
                                first_score = scores_list[0]
                                if isinstance(first_score, dict):
                                    # Ensure name and basic fields
                                    first_score['name'] = file_basenames[i] if file_basenames and i < len(file_basenames) else first_score.get('name', file_basenames[i])
                                    final_scores[i] = first_score
                                    logger.info(f"Recovered result for file {fd.get('filename')} via single-file retry")
                                    continue
                        # If retry did not yield a usable score, attach raw response to reasoning for easier debugging
                        if raw_retry:
                            final_scores[i]['reasoning'] = (final_scores[i].get('reasoning') or '') + f" Model raw response on retry: {raw_retry[:500]}"

                    # Additional targeted attempt: for files that returned a result but have no details or explicitly said 'No questions', ask the model to search for implicit Q/A and grade
                    retried_search_indices = set()
                    for i, s in enumerate(final_scores):
                        # Skip if details present
                        if s.get('details'):
                            continue
                        reason = (s.get('reasoning') or '').lower()
                        # Only attempt if not already retried and the prepared file exists and has content
                        if i in retried_search_indices:
                            continue
                        try:
                            fd = prepared[i]
                        except Exception:
                            fd = None
                        if not fd:
                            continue
                        content_text = (fd.get('content_processed') or '').strip()
                        if not content_text or len(content_text) < 10:
                            continue
                        if 'no questions' not in reason and s.get('score_percent') not in (None, 0):
                            # skip if the reason is not a 'no question' case and score is non-zero
                            continue

                        # Build an aggressive search-and-grade prompt that asks the model to hunt for implicit Q/A
                        search_parts = [
                            f"Title: {request.title or 'Grading Task'}\n",
                            "Instruction: The file below may not use explicit 'Question' markers. Search the content thoroughly for question-like text and the corresponding student answers. If you find none, say explicitly 'No questions found'. Otherwise, grade each student's answers and return ONLY JSON using this schema. Be conservative and do not hallucinate.",
                            "Schema:\n{ \"summary\": string, \"scores\": [{ \"name\": string, \"score_percent\": number, \"reasoning\": string, \"details\": [{\"question\": string, \"student_answer\": string, \"correct_answer\": string, \"is_correct\": boolean, \"feedback\": string}] }] }\n",
                            f"--- File: {fd.get('filename')} ({fd.get('file_type')}) ---\n",
                            content_text
                        ]
                        search_prompt = "\n".join(search_parts)

                        try:
                            resp = openrouter_service.generate(search_prompt)
                            if not resp.get('success'):
                                logger.debug(f"Search retry for file {fd.get('filename')} failed: {resp.get('error')}")
                                continue
                            raw = resp.get('response', '')
                            parsed = None
                            try:
                                parsed = json.loads(raw)
                            except Exception:
                                try:
                                    m = re.search(r"\{[\s\S]*\}", raw)
                                    if m:
                                        parsed = json.loads(m.group(0))
                                except Exception:
                                    parsed = None

                            if parsed and isinstance(parsed, dict):
                                scores_list = parsed.get('scores') or []
                                if isinstance(scores_list, list) and scores_list:
                                    first_score = scores_list[0]
                                    if isinstance(first_score, dict):
                                        first_score['name'] = fd.get('display_name') or first_score.get('name') or file_basenames[i]
                                        final_scores[i] = first_score
                                        retried_search_indices.add(i)
                                        logger.info(f"Recovered detailed grading for file {fd.get('filename')} via search-and-grade retry")
                                        continue
                            # If nothing usable, append raw response for debugging
                            if raw:
                                final_scores[i]['reasoning'] = (final_scores[i].get('reasoning') or '') + f" Model raw search response: {raw[:500]}"
                        except Exception:
                            logger.debug(f"Exception during search retry for file {fd.get('filename')}", exc_info=True)

                except Exception:
                    # keep silent on retry failures but log at debug level
                    import traceback
                    logger.debug("Exception during per-file retry: " + traceback.format_exc())
        except Exception:
            # If anything goes wrong here, silently continue to cleanup and return available results
            pass

        # Clean up temporary files
        for file_path in file_paths_to_cleanup:
            try:
                if file_path.exists():
                    file_path.unlink()
            except:
                pass
        # Clean up metadata files
        for meta_path in meta_paths_to_cleanup:
            try:
                if meta_path and meta_path.exists():
                    meta_path.unlink()
            except:
                pass
        
        # Return combined results across all batches
        return GenerateResponse(
            success=True,
            result=combined_raw,
            summary=combined_summary,
            scores=agg_scores
        )
    
    except HTTPException:
        raise
    except Exception as e:
        # Clean up on error
        for file_path in file_paths_to_cleanup:
            try:
                if file_path.exists():
                    file_path.unlink()
            except:
                pass
        
        raise HTTPException(
            status_code=500,
            detail=f"Error generating content: {str(e)}"
        )


@app.post("/evaluate-git", response_model=GitEvaluateResponse)
async def evaluate_git_repository(
    request: GitEvaluateRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Evaluate a GitHub repository and provide project information, purpose, and details.
    This endpoint processes all nested files from the repository and provides comprehensive analysis.
    """
    if not request.github_url or not request.github_url.strip():
        # Return graceful error instead of raising HTTPException so frontend
        # can show a friendly message without a red X / 4xx status
        return GitEvaluateResponse(
            success=False,
            result=None,
            error="GitHub URL is required",
            raw_response=None,
        )
    
    github_url = request.github_url.strip()
    
    # Validate GitHub URL format
    if 'github.com' not in github_url.lower():
        return GitEvaluateResponse(
            success=False,
            result=None,
            error="Invalid GitHub URL. Please provide a valid GitHub repository URL",
            raw_response=None,
        )
    
    try:
        logger.info(f"Evaluating GitHub repository: {github_url}")
        
        # Fetch all files from the repository (including nested files)
        # Increase max_files limit for comprehensive evaluation
        max_files = int(os.getenv("GIT_EVAL_MAX_FILES", "200"))
        github_files = github_service.fetch_repository_files(github_url, max_files=max_files)
        
        if not github_files:
            # Instead of raising 404, return success=False so the frontend
            # gets a normal 200 response with a clear error message.
            return GitEvaluateResponse(
                success=False,
                result=None,
                error="No files found in the repository. Please check if the repository is public and accessible.",
                raw_response=None,
            )
        
        logger.info(f"Fetched {len(github_files)} files from repository")
        
        # Evaluate the repository using the GitEvaluator
        evaluation_result = git_evaluator.evaluate_repository(github_url, github_files)
        
        if not evaluation_result.get("success"):
            error_msg = evaluation_result.get("error", "Unknown error during evaluation")
            return GitEvaluateResponse(
                success=False,
                result=None,
                error=f"Error evaluating repository: {error_msg}",
                raw_response=evaluation_result.get("raw_response"),
            )
        
        # Return the evaluation results
        return GitEvaluateResponse(
            success=True,
            result=evaluation_result.get("result"),
            raw_response=evaluation_result.get("raw_response")
        )
    
    except HTTPException as http_exc:
        # Convert unexpected HTTPExceptions into a structured 200 response
        logger.error(f"HTTP error during Git repository evaluation: {http_exc.detail}")
        return GitEvaluateResponse(
            success=False,
            result=None,
            error=str(http_exc.detail),
            raw_response=None,
        )
    except Exception as e:
        logger.error(f"Error evaluating Git repository: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error evaluating repository: {str(e)}"
        )


@app.post("/grade-git", response_model=GitGradeResponse)
async def grade_git_repository(
    request: GitGradeRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Grade a GitHub repository against the user's description/rules.

    Example rule in description:
      - "backend technology_stack is python and fastapi"
    The service will analyze the actual repository tech stack and other rules
    from the description, then return a score and detailed rule-by-rule results.
    """
    github_url = (request.github_url or "").strip()
    description = (request.description or "").strip()

    if not github_url:
        return GitGradeResponse(
            success=False,
            result=None,
            error="GitHub URL is required",
            raw_response=None,
        )

    if "github.com" not in github_url.lower():
        return GitGradeResponse(
            success=False,
            result=None,
            error="Invalid GitHub URL. Please provide a valid GitHub repository URL",
            raw_response=None,
        )

    # More robust check: ensure description is not just whitespace
    if not description or not description.strip():
        return GitGradeResponse(
            success=False,
            result=None,
            error="Description with grading rules is required. Please provide at least one rule or requirement.",
            raw_response=None,
        )

    try:
        logger.info(f"Grading GitHub repository: {github_url} against user rules")

        max_files = int(os.getenv("GIT_EVAL_MAX_FILES", "200"))
        github_files = github_service.fetch_repository_files(github_url, max_files=max_files)

        if not github_files:
            return GitGradeResponse(
                success=False,
                result=None,
                error="No files found in the repository. Please check if the repository is public and accessible.",
                raw_response=None,
            )

        grading_result = git_evaluator.grade_repository(github_url, github_files, description)

        if not grading_result.get("success"):
            return GitGradeResponse(
                success=False,
                result=None,
                error=grading_result.get("error", "Unknown error during grading"),
                raw_response=grading_result.get("raw_response"),
            )

        return GitGradeResponse(
            success=True,
            result=grading_result.get("result"),
            raw_response=grading_result.get("raw_response"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error grading Git repository: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error grading repository: {str(e)}"
        )


@app.get("/openrouter/status")
def check_openrouter_status():
    """Check if Ollama is running and available"""
    is_connected = openrouter_service.check_connection()
    models = openrouter_service.list_models() if is_connected else []
    
    return {
        "connected": is_connected,
        "base_url": openrouter_service.base_url,
        "default_model": openrouter_service.model,
        "available_models": models
    }


@app.get("/debug/extracted/{file_id}")
def debug_extracted(file_id: str, current_user: User = Depends(get_current_user)):
    """Return the extracted text and a quick QA hint for a given uploaded file id for debugging extraction issues."""
    file_path = None
    for saved_file in UPLOAD_DIR.glob(f"{file_id}.*"):
        if saved_file.name == f"{file_id}.meta.json":
            continue
        file_path = saved_file
        break

    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File with ID {file_id} not found")

    file_data = file_processor.read_file(str(file_path))
    content = file_data.get('content', '') or ''

    # Quick QA extractor (same heuristics as the main batch pipeline)
    def extract_qa_pairs_local(text: str):
        qa = []
        if not text or not isinstance(text, str):
            return qa
        lines = [l.rstrip() for l in text.splitlines()]
        i = 0
        question_re = re.compile(r"^\s*(?:Question\b[:\s]*|Q\d*[:\s]*|Q\d+\b|\d+\s*[\.)\-:])", flags=re.IGNORECASE)
        answer_marker_re = re.compile(r"\bAnswer\b[:\s]*", flags=re.IGNORECASE)

        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if '\t' in line:
                cells = [c.strip() for c in line.split('\t')]
                lc = [c.lower() for c in cells]
                if any('question' in c for c in lc) or any('answer' in c for c in lc) or any('q' == c for c in lc):
                    q = cells[0]
                    a = cells[1] if len(cells) > 1 else ''
                    qa.append({'question': q, 'answer': a})
                    i += 1
                    continue
            if question_re.search(line) or '?' in line:
                qtext = re.sub(r"^\s*(?:Question\b[:\s]*|Q\d*[:\s]*|\d+\s*[\.)\-:]\s*)", '', line, flags=re.IGNORECASE)
                ans_lines = []
                j = i + 1
                while j < len(lines):
                    l = lines[j].strip()
                    if not l:
                        j += 1
                        if j < len(lines) and question_re.search(lines[j]):
                            break
                        continue
                    if question_re.search(l):
                        break
                    if answer_marker_re.search(l):
                        a = answer_marker_re.sub('', l).strip()
                        if a:
                            ans_lines.append(a)
                        j += 1
                        while j < len(lines) and not question_re.search(lines[j]):
                            if lines[j].strip():
                                ans_lines.append(lines[j].strip())
                            j += 1
                        break
                    ans_lines.append(l)
                    j += 1
                answer = ' '.join(ans_lines).strip()
                qa.append({'question': qtext.strip() or line, 'answer': answer or None})
                i = j
                continue
            i += 1
        return qa

    qa_pairs = extract_qa_pairs_local(content)
    has_questions = bool(qa_pairs) or bool(re.search(r"\bQ(?:uestion)?\s*\d+\b|\bQ\d+\b|\bQuestion:\b|\bName:\b|\bStudent:\b|\bCandidate:\b|^\d+\.\s", content, flags=re.IGNORECASE | re.MULTILINE))

    return {
        'filename': file_data.get('filename'),
        'extension': file_data.get('extension'),
        'file_type': file_data.get('file_type'),
        'content': content,
        'qa_pairs': qa_pairs,
        'has_questions': has_questions
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

