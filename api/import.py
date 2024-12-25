import json
import subprocess
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException, Form, Query, UploadFile
from typing import List, Optional
import os
from pydantic import SecretStr

from fastapi.responses import FileResponse

app = FastAPI()
final_paths = []

def execute_medusa_command():
    try:
        command = [
            "./medusa", "export", os.environ["PATH"],
            "--address", os.environ["ADDRESS"],
            "--token", os.environ["TOKEN"],
            "--format", "json"
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        # Retourner la sortie JSON parsée
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Command failed: {e.stderr}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to parse JSON output from medusa")

def generate_paths(data, prefix=""):
    paths = []
    for key, value in data.items():
        if not isinstance(value, dict):
            # Si la valeur n'est pas un dictionnaire, on saute cette clé
            continue
        current_path = f"{prefix}/{key}" if prefix else key
        paths.append(current_path)
        # Récursion pour les sous-dictionnaires
        paths.extend(generate_paths(value, current_path))
    return paths


@app.post("/env")
async def export_env(
    address: str = Query(..., description="Vault URL"),
    token: SecretStr = Query(..., description="Vault Token"),
    secret_root: str = Query(..., description="Root secret")
):
    global final_paths  # Permet de modifier la variable globale

    try:
        # Définir les variables d'environnement
        os.environ["ADDRESS"] = address
        os.environ["TOKEN"] = token.get_secret_value()
        os.environ["PATH"] = secret_root
        
        print("Executing medusa command...")
        secret_paths = execute_medusa_command()  # Retourne un dictionnaire
        print("Command executed successfully:", secret_paths)
        
        # Générer les chemins et les stocker dans la variable globale
        final_paths = generate_paths(secret_paths)
        print("Generated paths:", final_paths)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process ENV variables: {str(e)}")

    return {"message": "ENV variables created successfully", "paths": final_paths}


@app.get("/get_paths")
async def get_paths():
    return final_paths

@app.post("/import")
async def import_to_vault(
    address: str = Form(...),
    token: str = Form(...),
    path: str = Form(...),
    decrypt: bool = Form(False),
    files: List[UploadFile] = []
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided for import.")

    local_file_paths = []
    try:
        for file in files:
            file_location = f"/tmp/{file.filename}"
            with open(file_location, "wb") as f:
                content = await file.read()
                f.write(content)
            local_file_paths.append(file_location)

        command = [
            "./medusa", "import", path,
            "--address", address,
            "--token", token,
            "--decrypt" if decrypt else "",
            "--insecure"
        ]
        command.extend(local_file_paths)
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Medusa import failed: {result.stderr}")

        return {"message": "Files imported successfully", "files": local_file_paths}
    finally:
        for file_path in local_file_paths:
            if os.path.exists(file_path):
                os.remove(file_path)

@app.post("/export")
async def export_from_vault(
    address: str = Query(..., description="Vault URL"),
    token: str = Query(..., description="Vault Token"),
    path: str = Query(..., description="Secret path"),
    decrypt: bool = Form(False),
    file_name: Optional[str] = Query(None, description="Choose file name"),
    output_format: str = Query("yaml", description="Choose file format", enum=("yaml", "json"))
):
    # Si file_name est vide, créer un nom par défaut basé sur le path
    file_name_to_use = file_name if file_name else path.replace("/", "_")
    file_name_to_use = f"{file_name_to_use}.{output_format}"

    command = [
        "./medusa", "export", path,
        "--address", address,
        "--token", token,
        "--decrypt" if decrypt else "",
        "--output", file_name_to_use,
        "--format", output_format,
        "--insecure"
    ]

    # Nettoyer la commande pour éviter des chaînes vides
    command = [arg for arg in command if arg]

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Medusa export failed: {result.stderr}")

    # Vérification si le fichier a bien été créé
    if not os.path.exists(file_name_to_use):
        raise HTTPException(status_code=500, detail="File was not created.")

    # Retourner le fichier pour téléchargement
    return FileResponse(
        path=file_name_to_use,
        filename=file_name_to_use,
        media_type="application/octet-stream"
    )

@app.post("/advenced_export")
async def export_from_vault(
    #path: str = Query(..., description="Secret path"),
    decrypt: bool = Form(False),
    file_name: Optional[str] = Query(None, description="Choose file name"),
    output_format: str = Query("yaml", description="Choose file format", enum=("yaml", "json")),
    available_paths: str = Query(description="Choose file name",enum=final_paths),
):
    # Si file_name est vide, créer un nom par défaut basé sur le path
    file_name_to_use = file_name if file_name else available_paths.replace("/", "_")
    file_name_to_use = f"{file_name_to_use}.{output_format}"

    command = [
        "./medusa", "export", available_paths,
        "--address", os.environ["ADDRESS"],
        "--token", os.environ["TOKEN"],
        "--decrypt" if decrypt else "",
        "--output", file_name_to_use,
        "--format", output_format,
        "--insecure"
    ]

    # Nettoyer la commande pour éviter des chaînes vides
    command = [arg for arg in command if arg]

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Medusa export failed: {result.stderr}")

    # Vérification si le fichier a bien été créé
    if not os.path.exists(file_name_to_use):
        raise HTTPException(status_code=500, detail="File was not created.")

    # Retourner le fichier pour téléchargement
    return FileResponse(
        path=file_name_to_use,
        filename=file_name_to_use,
        media_type="application/octet-stream"
    )