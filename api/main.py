import json
import subprocess
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException, Form, Query, UploadFile
from typing import List, Optional
import os
from pydantic import SecretStr

from fastapi.responses import FileResponse
import yaml

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
    

def execute_medusa_command(address, token, path):
    try:
        command = [
            "./medusa", "export", path,
            "--address", address,
            "--token", token,
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



@app.get("/get_paths")
async def get_paths(    
    address: str = Query(..., description="Vault URL"),
    token: SecretStr = Query(..., description="Vault Token"),
    secret_root: str = Query(..., description="Root secret")
):
    global final_paths 
    try:

        secret_paths = execute_medusa_command(address,token,secret_root)  
        final_paths = generate_paths(secret_paths)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch secret paths: {str(e)}")

    return {"message": "Secret paths fetched successfully", "available path secrets": final_paths}


@app.post("/import")
async def import_to_vault(
    address: str = Query(..., description="Vault URL"),
    token: str = Query(..., description="Vault Token"),
    path: str = Query(..., description="Secret path to import"),
    decrypt: bool = Query("False", description="Choose file format", enum=("False", "True")),
    engine_type:str = Query("kv2", description="Choose file format", enum=("kv2", "kv1")),
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
            "--engine-type", engine_type,
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
    output_format: str = Query("yaml", description="Choose file format", enum=("yaml", "json")),
    engine_type:str = Query("kv2", description="Choose file format", enum=("kv2", "kv1"))
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
        "--engine-type", engine_type,
        "--insecure"
    ]
    command = [arg for arg in command if arg]

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Medusa export failed: {result.stderr}")

    if not os.path.exists(file_name_to_use):
        raise HTTPException(status_code=500, detail="File was not created.")

    return FileResponse(
        path=file_name_to_use,
        filename=file_name_to_use,
        media_type="application/octet-stream"
    )


@app.post("/copy_secret")
async def copy(
    address: str = Query(..., description="Vault URL"),
    token: str = Query(..., description="Vault Token"),
    source_path: str = Query(..., description="Source secret path"),
    target_path: str = Query(..., description="Target secret path"),
    engine_type:str = Query("kv2", description="Choose file format", enum=("kv2", "kv1"))
):
    try:
        command_copy = [
        "./medusa", "copy", source_path, target_path,
        "--address", address,
        "--token", token,
        "--engine-type", engine_type
    ]
        copy_result = subprocess.run(command_copy, capture_output=True, text=True)
        print(copy_result)

        if copy_result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete secret: {copy_result.stderr}"
            )
        return {
            "message": f"Secrets from '{source_path}' copied successfully",
            "source_path": source_path,
            "target_path": target_path,
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete secret: {str(e)}")

@app.post("/move_secret")
async def move_secret(
    address: str = Query(..., description="Vault URL"),
    token: str = Query(..., description="Vault Token"),
    source_path: str = Query(..., description="Source secret path"),
    target_path: str = Query(..., description="Target secret path"),
    engine_type:str = Query("kv2", description="Choose file format", enum=("kv2", "kv1")),
):
    try:
        command_move = [
        "./medusa", "move", source_path, target_path,
        "--address", address,
        "--auto-approve",
        "--token", token,
        "--engine-type", engine_type
    ]
        move_result = subprocess.run(command_move, capture_output=True, text=True)
        print(move_result)

        if move_result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete secret: {move_result.stderr}"
            )
        return {
            "message": f"Secrets from '{source_path}' copied successfully",
            "source_path": source_path,
            "target_path": target_path,
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete secret: {str(e)}")


@app.post("/from_old_to_new")
async def migrate(
    old_address: str = Query(..., description="Old Vault URL"),
    old_token: str = Query(..., description="Vault Token"),
    old_path: str = Query(..., description="Secret path"),
    old_engine_type:str = Query("kv2", description="Choose file format", enum=("kv2", "kv1")), 
    new_address: str = Query(..., description="New Vault URL"),
    new_token: str = Query(..., description="Vault Token"),
    new_path: str = Query(..., description="Secret path"),
    engine_type:str = Query("kv2", description="Choose file format", enum=("kv2", "kv1")),
    decrypt: bool = Form(False)
):
    try:
        export_old_command = [
        "./medusa", "export", old_path,
        "--address", old_address,
        "--token", old_token,
        "--engine-type", old_engine_type,
        "--output", "/tmp/export_old.yaml",
        "--insecure"

    ]
        export_result = subprocess.run(export_old_command, capture_output=True, text=True)

        if export_result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to export secret from old vault: {export_result.stderr}"
            )
        file_name="/tmp/export_old.yaml"
        import_new_command=[
        "./medusa", "import", new_path, file_name,
        "--address", new_address,
        "--token", new_token,
        "--engine-type", engine_type,
        "--insecure"
    ]
        import_result=subprocess.run(import_new_command, capture_output=True, text=True)
        print(import_result.stdout)

        if import_result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to import secret: {export_result.stderr}"
            )
        return {
            "message": f"Secrets from '{old_address}' copied successfully to '{ new_address }'"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to migrate secrets: {str(e)}")


@app.delete("/delete")
async def delete_secret(
    address: str = Query(..., description="Vault URL"),
    token: SecretStr = Query(..., description="Vault Token"),
    secret_path: str = Query(..., description="Secret path")
):
    try:
        command_delete = [
            "./medusa", "delete", secret_path,
            "--address", address,
            "--token", token.get_secret_value(),
            "--auto-approve",
            "--insecure"
        ]

        delete_result = subprocess.run(
            command_delete,
            capture_output=True,
            text=True
        )
        if delete_result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete secret: {delete_result.stderr}"
            )
        return {"message": "Secret deleted successfully", "secret_path": secret_path}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete secret: {str(e)}")

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

        secret_paths = execute_medusa_command()
        print("Command executed successfully:", secret_paths)
        

        final_paths = generate_paths(secret_paths)
        print("Generated paths:", final_paths)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process ENV variables: {str(e)}")

    return {"message": "ENV variables created successfully", "available path secrets": final_paths}

@app.post("/advenced_export")
async def export_from_vault(
    decrypt: bool = Form(False),
    file_name: Optional[str] = Query(None, description="Choose file name"),
    output_format: str = Query("yaml", description="Choose file format", enum=("yaml", "json")),
    available_paths: str = Query(description="Secret path"),
    engine_type:str = Query("kv2", description="Choose file format", enum=("kv2", "kv1"))
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
        "--engine-type", engine_type,
        "--insecure"
    ]

    # Nettoyer la commande pour éviter des chaînes vides
    command = [arg for arg in command if arg]

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Medusa export failed: {result.stderr}")

    if not os.path.exists(file_name_to_use):
        raise HTTPException(status_code=500, detail="File was not created.")
    
    return FileResponse(
        path=file_name_to_use,
        filename=file_name_to_use,
        media_type="application/octet-stream"
    )    