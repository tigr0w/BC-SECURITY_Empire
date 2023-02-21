import os
import shutil


def remove_dir_contents(path: str) -> None:
    """
    Removes all files and directories in a directory.
    Keeps the .keep and .gitignore that reserve the directory.
    """
    for root, dirs, files in os.walk(path):
        for f in files:
            if f.endswith(".keep") or f.endswith(".gitignore"):
                continue
            os.unlink(os.path.join(root, f))
        for d in dirs:
            shutil.rmtree(os.path.join(root, d))


def remove_file(path: str) -> None:
    """
    Removes a file. If the file doesn't exist, nothing happens.
    """
    if os.path.exists(path):
        os.remove(path)
