"""
Description: Service layer implementation for EncryptionResult.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import os
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.backends import default_backend

class EncryptionResult:
    def __init__(self, salt, nonce, algorithm, kdf, kdf_params, plaintext_size, ciphertext_size):
        self.salt = salt
        self.nonce = nonce
        self.algorithm = algorithm
        self.kdf = kdf
        self.kdf_params = kdf_params
        self.plaintext_size = plaintext_size
        self.ciphertext_size = ciphertext_size

class EncryptionService:
    CHUNK_SIZE = 64 * 1024  # 64KB chunks for memory efficiency

    @staticmethod
    def derive_key(password: str, salt: bytes, n: int, r: int, p: int, length: int = 32) -> bytes:
        """Derives a key from a password and salt using scrypt."""
        kdf = Scrypt(
            salt=salt,
            length=length,
            n=n,
            r=r,
            p=p,
            backend=default_backend()
        )
        return kdf.derive(password.encode())

    @staticmethod
    def encrypt_stream(input_file, output_file, password: str, n: int, r: int, p: int) -> EncryptionResult:
        """Encrypts a stream into another stream using AES-256-GCM in chunks."""
        salt = os.urandom(16)
        nonce = os.urandom(12)
        key = EncryptionService.derive_key(password, salt, n, r, p)

        encryptor = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce),
            backend=default_backend()
        ).encryptor()

        plaintext_size = 0
        ciphertext_size = 0

        while True:
            chunk = input_file.read(EncryptionService.CHUNK_SIZE)
            if not chunk:
                break
            plaintext_size += len(chunk)
            encrypted_chunk = encryptor.update(chunk)
            output_file.write(encrypted_chunk)
            ciphertext_size += len(encrypted_chunk)

        encryptor.finalize()
        tag = encryptor.tag
        output_file.write(tag)
        ciphertext_size += len(tag)

        return EncryptionResult(
            salt=base64.b64encode(salt).decode('utf-8'),
            nonce=base64.b64encode(nonce).decode('utf-8'),
            algorithm="AES-256-GCM",
            kdf="scrypt",
            kdf_params={"n": n, "r": r, "p": p, "length": 32},
            plaintext_size=plaintext_size,
            ciphertext_size=ciphertext_size
        )

    @staticmethod
    def decrypt_stream(input_file, output_file, password: str, salt_b64: str, nonce_b64: str, metadata: dict) -> None:
        """Decrypts a stream into another stream using AES-256-GCM and stored metadata."""
        salt = base64.b64decode(salt_b64)
        nonce = base64.b64decode(nonce_b64)
        kdf_params = metadata['kdf_params']

        key = EncryptionService.derive_key(
            password,
            salt,
            kdf_params['n'],
            kdf_params['r'],
            kdf_params['p'],
            kdf_params.get('length', 32)
        )

        # In our implementation, the last 16 bytes of the file are the GCM tag
        # We need to read everything but the tag first.
        # Since it's a stream, we might not know the size easily if it's a pipe,
        # but for files we can seek.

        input_file.seek(0, os.SEEK_END)
        file_size = input_file.tell()
        input_file.seek(0)

        if file_size < 16:
            raise ValueError("Encrypted file too small (missing tag)")

        data_size = file_size - 16

        input_file.seek(data_size)
        tag = input_file.read(16)
        input_file.seek(0)

        decryptor = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce, tag),
            backend=default_backend()
        ).decryptor()

        bytes_read = 0
        while bytes_read < data_size:
            to_read = min(EncryptionService.CHUNK_SIZE, data_size - bytes_read)
            chunk = input_file.read(to_read)
            if not chunk:
                break
            bytes_read += len(chunk)
            output_file.write(decryptor.update(chunk))

        # Verify tag
        output_file.write(decryptor.finalize())

    @staticmethod
    def is_encryption_available() -> bool:
        try:
            import cryptography
            return True
        except ImportError:
            return False

encryption_service = EncryptionService()
