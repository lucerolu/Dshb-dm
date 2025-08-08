import streamlit_authenticator as stauth

passwords = ['Authdms30']

# Crear instancia vacía
hasher = stauth.Hasher()

# Generar hash para cada contraseña
hashed_passwords = [hasher.hash(password) for password in passwords]

print(hashed_passwords)
