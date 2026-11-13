"""NEXUS AI - Modular Full-Stack Code & Test Generator.
Generates complete backend (FastAPI, SQLAlchemy, Pydantic), responsive frontend (HTML5/CSS3/JS),
and comprehensive pytest test suites for scaffolded projects.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional


def generate_full_stack_project(architecture: Dict[str, Any]) -> Dict[str, str]:
    """Generate complete implementation code for all files in the architecture."""
    proj_dir = Path(architecture["project_dir"])
    proj_dir.mkdir(parents=True, exist_ok=True)

    domain = architecture.get("domain", "general")
    title = architecture.get("slug", "Application").replace("_", " ").title()

    files_content: Dict[str, str] = {}

    # 1. requirements.txt
    files_content["requirements.txt"] = (
        "fastapi>=0.100.0\n"
        "uvicorn>=0.22.0\n"
        "sqlalchemy>=2.0.0\n"
        "pydantic>=2.0.0\n"
        "pytest>=7.0.0\n"
        "httpx>=0.24.0\n"
    )

    # 2. database.py
    files_content["database.py"] = (
        "from sqlalchemy import create_engine\n"
        "from sqlalchemy.ext.declarative import declarative_base\n"
        "from sqlalchemy.orm import sessionmaker\n\n"
        "SQLALCHEMY_DATABASE_URL = 'sqlite:///./app.db'\n\n"
        "engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={'check_same_thread': False})\n"
        "SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)\n"
        "Base = declarative_base()\n\n"
        "def get_db():\n"
        "    db = SessionLocal()\n"
        "    try:\n"
        "        yield db\n"
        "    finally:\n"
        "        db.close()\n"
    )

    # 3. models.py
    files_content["models.py"] = (
        "from sqlalchemy import Column, Integer, String, Boolean, DateTime\n"
        "from datetime import datetime\n"
        "from database import Base\n\n"
        "class Record(Base):\n"
        "    __tablename__ = 'records'\n\n"
        "    id = Column(Integer, primary_key=True, index=True)\n"
        "    title = Column(String, index=True, nullable=False)\n"
        "    description = Column(String, default='')\n"
        "    is_active = Column(Boolean, default=True)\n"
        "    created_at = Column(DateTime, default=datetime.utcnow)\n"
    )

    # 4. schemas.py
    files_content["schemas.py"] = (
        "from pydantic import BaseModel\n"
        "from typing import Optional\n"
        "from datetime import datetime\n\n"
        "class RecordBase(BaseModel):\n"
        "    title: str\n"
        "    description: Optional[str] = ''\n"
        "    is_active: Optional[bool] = True\n\n"
        "class RecordCreate(RecordBase):\n"
        "    pass\n\n"
        "class RecordResponse(RecordBase):\n"
        "    id: int\n"
        "    created_at: datetime\n\n"
        "    class Config:\n"
        "        orm_mode = True\n"
    )

    # 5. main.py
    files_content["main.py"] = (
        "from fastapi import FastAPI, Depends, HTTPException\n"
        "from fastapi.staticfiles import StaticFiles\n"
        "from fastapi.responses import FileResponse\n"
        "from sqlalchemy.orm import Session\n"
        "from typing import List\n"
        "import os\n\n"
        "from database import engine, Base, get_db\n"
        "from models import Record\n"
        "from schemas import RecordCreate, RecordResponse\n\n"
        "Base.metadata.create_all(bind=engine)\n\n"
        "app = FastAPI(title='" + title + " API')\n\n"
        "os.makedirs('static', exist_ok=True)\n"
        "app.mount('/static', StaticFiles(directory='static'), name='static')\n\n"
        "@app.get('/')\n"
        "def read_index():\n"
        "    return FileResponse('static/index.html')\n\n"
        "@app.get('/health')\n"
        "def health():\n"
        "    return {'status': 'healthy', 'app': '" + title + "'}\n\n"
        "@app.get('/api/records', response_model=List[RecordResponse])\n"
        "def get_records(db: Session = Depends(get_db)):\n"
        "    return db.query(Record).all()\n\n"
        "@app.post('/api/records', response_model=RecordResponse)\n"
        "def create_record(item: RecordCreate, db: Session = Depends(get_db)):\n"
        "    db_record = Record(title=item.title, description=item.description, is_active=item.is_active)\n"
        "    db.add(db_record)\n"
        "    db.commit()\n"
        "    db.refresh(db_record)\n"
        "    return db_record\n\n"
        "@app.delete('/api/records/{record_id}')\n"
        "def delete_record(record_id: int, db: Session = Depends(get_db)):\n"
        "    db_record = db.query(Record).filter(Record.id == record_id).first()\n"
        "    if not db_record:\n"
        "        raise HTTPException(status_code=404, detail='Record not found')\n"
        "    db.delete(db_record)\n"
        "    db.commit()\n"
        "    return {'status': 'deleted', 'id': record_id}\n"
    )

    # 6. static/index.html
    files_content["static/index.html"] = (
        "<!DOCTYPE html>\n"
        "<html lang='en'>\n"
        "<head>\n"
        "    <meta charset='UTF-8'>\n"
        "    <meta name='viewport' content='width=device-width, initial-scale=1.0'>\n"
        "    <title>" + title + "</title>\n"
        "    <link rel='stylesheet' href='/static/style.css'>\n"
        "</head>\n"
        "<body>\n"
        "    <div class='container'>\n"
        "        <header>\n"
        "            <h1>" + title + "</h1>\n"
        "            <p>Generated autonomously by NEXUS AI</p>\n"
        "        </header>\n"
        "        <main>\n"
        "            <form id='recordForm'>\n"
        "                <input type='text' id='titleInput' placeholder='Enter title' required>\n"
        "                <input type='text' id='descInput' placeholder='Description'>\n"
        "                <button type='submit'>Add Record</button>\n"
        "            </form>\n"
        "            <div id='recordList' class='record-list'></div>\n"
        "        </main>\n"
        "    </div>\n"
        "    <script src='/static/app.js'></script>\n"
        "</body>\n"
        "</html>\n"
    )

    # 7. static/style.css
    files_content["static/style.css"] = (
        "* { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }\n"
        "body { background: #0f172a; color: #f8fafc; display: flex; justify-content: center; padding: 2rem; }\n"
        ".container { max-width: 700px; width: 100%; }\n"
        "header { margin-bottom: 2rem; border-bottom: 1px solid #334155; padding-bottom: 1rem; }\n"
        "h1 { color: #38bdf8; }\n"
        "form { display: flex; gap: 0.5rem; margin-bottom: 2rem; }\n"
        "input { padding: 0.75rem; border-radius: 6px; border: 1px solid #334155; background: #1e293b; color: white; flex: 1; }\n"
        "button { padding: 0.75rem 1.5rem; background: #38bdf8; color: #0f172a; font-weight: bold; border: none; border-radius: 6px; cursor: pointer; }\n"
        "button:hover { background: #0284c7; }\n"
        ".record-item { background: #1e293b; padding: 1rem; border-radius: 6px; margin-bottom: 0.75rem; display: flex; justify-content: space-between; align-items: center; }\n"
    )

    # 8. static/app.js
    files_content["static/app.js"] = (
        "document.addEventListener('DOMContentLoaded', () => {\n"
        "    const form = document.getElementById('recordForm');\n"
        "    const list = document.getElementById('recordList');\n\n"
        "    async function loadRecords() {\n"
        "        const res = await fetch('/api/records');\n"
        "        const data = await res.json();\n"
        "        list.innerHTML = data.map(r => `\n"
        "            <div class='record-item'>\n"
        "                <div>\n"
        "                    <strong>${r.title}</strong>\n"
        "                    <p>${r.description || ''}</p>\n"
        "                </div>\n"
        "                <button onclick='deleteRecord(${r.id})'>Delete</button>\n"
        "            </div>\n"
        "        `).join('');\n"
        "    }\n\n"
        "    window.deleteRecord = async (id) => {\n"
        "        await fetch(`/api/records/${id}`, { method: 'DELETE' });\n"
        "        loadRecords();\n"
        "    };\n\n"
        "    form.addEventListener('submit', async (e) => {\n"
        "        e.preventDefault();\n"
        "        const title = document.getElementById('titleInput').value;\n"
        "        const description = document.getElementById('descInput').value;\n"
        "        await fetch('/api/records', {\n"
        "            method: 'POST',\n"
        "            headers: { 'Content-Type': 'application/json' },\n"
        "            body: JSON.stringify({ title, description, is_active: true })\n"
        "        });\n"
        "        form.reset();\n"
        "        loadRecords();\n"
        "    });\n\n"
        "    loadRecords();\n"
        "});\n"
    )

    # 9. tests/__init__.py
    files_content["tests/__init__.py"] = ""

    # 10. tests/test_app.py
    files_content["tests/test_app.py"] = (
        "import pytest\n"
        "from fastapi.testclient import TestClient\n"
        "from main import app\n\n"
        "client = TestClient(app)\n\n"
        "def test_health():\n"
        "    response = client.get('/health')\n"
        "    assert response.status_code == 200\n"
        "    assert response.json()['status'] == 'healthy'\n\n"
        "def test_create_and_read_record():\n"
        "    payload = {'title': 'Initial Test Item', 'description': 'Testing creation', 'is_active': True}\n"
        "    res = client.post('/api/records', json=payload)\n"
        "    assert res.status_code == 200\n"
        "    data = res.json()\n"
        "    assert data['title'] == 'Initial Test Item'\n"
        "    assert 'id' in data\n\n"
        "    # Read\n"
        "    list_res = client.get('/api/records')\n"
        "    assert list_res.status_code == 200\n"
        "    items = list_res.json()\n"
        "    assert any(i['id'] == data['id'] for i in items)\n\n"
        "def test_delete_record():\n"
        "    # Create then delete\n"
        "    item = client.post('/api/records', json={'title': 'To Delete'}).json()\n"
        "    del_res = client.delete(f\"/api/records/{item['id']}\")\n"
        "    assert del_res.status_code == 200\n"
        "    assert del_res.json()['status'] == 'deleted'\n"
    )

    # 11. README.md
    files_content["README.md"] = (
        f"# {title}\n\n"
        "Autonomously generated full-stack application engineered by **NEXUS AI DeveloperAgent**.\n\n"
        "## Architecture\n"
        "- **Backend**: FastAPI with SQLAlchemy ORM and Pydantic validation\n"
        "- **Database**: SQLite\n"
        "- **Frontend**: HTML5, Modern CSS, Vanilla JavaScript\n"
        "- **Testing**: Pytest with FastApi TestClient\n\n"
        "## Running the Application\n"
        "```bash\n"
        "pip install -r requirements.txt\n"
        "uvicorn main:app --reload --port 8010\n"
        "```\n\n"
        "## Running Tests\n"
        "```bash\n"
        "pytest tests/\n"
        "```\n"
    )

    # Write all files to disk
    written_files = {}
    for rel_path, content in files_content.items():
        dest = proj_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        written_files[rel_path] = str(dest.resolve())

    return written_files

