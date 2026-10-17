try:
    from cryptography.fernet import Fernet
    print("IMPORT OK")
except Exception:
    import traceback
    traceback.print_exc()
input("enter dabao...")
