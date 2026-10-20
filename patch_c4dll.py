"""Patch DisciplesGL 2.0.2 (C4dll-R.dll) so its animation-speed hook never returns a step below 4.

Bug: the hook at RVA 0x13080 (installed over the game's `call 0x61a5fd` at 0x4f5d5a) computes
    *step = step * (fast ? 10 : 20) * GameSpeed / (3 * refreshRate)
with unsigned integer division. The game then halves the step up to twice. At 240 Hz the result
can be 0, and the game's animation loop `for (d = 0; d < len; d += step)` never ends.

Fix: both exits of the hook (`mov [esi],eax; mov al,bl; pop esi; pop ebx; ret`) jump to a cave
at the end of .text that clamps eax to >= 4 (so it survives two halvings) before the same tail.

usage: python -I patch_c4dll.py <original.dll> <patched.dll>
"""
import hashlib, struct, sys

EXPECTED_SHA256 = '4730a43e94d2f6a4ba512564cf58a4f0e3b8c0e927fe293a1504f30463fb2107'
TAIL = bytes.fromhex('89 06 8a c3 5e 5b c3')          # mov [esi],eax; mov al,bl; pop esi; pop ebx; ret
SITES = (0x130BD, 0x130E3)                            # speed-enabled exit, speed-disabled exit
CAVE_RVA = 0x35740                                    # 16-aligned, in .text's zero raw slack
MIN_STEP = 4
CAVE = (bytes.fromhex('83 f8') + bytes([MIN_STEP])    # cmp eax, 4
        + bytes.fromhex('73 05')                      # jae +5
        + b'\xb8' + struct.pack('<I', MIN_STEP)       # mov eax, 4
        + TAIL)                                       # original tail


def checksum(data, csum_off):
    """PE checksum, as computed by CheckSumMappedFile."""
    total = 0
    padded = data + b'\0' * (len(data) & 1)
    for i in range(0, len(padded), 2):
        if i == csum_off or i == csum_off + 2:
            continue
        total += struct.unpack_from('<H', padded, i)[0]
        total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (total + len(data)) & 0xFFFFFFFF


def main(src, dst):
    data = bytearray(open(src, 'rb').read())
    if hashlib.sha256(data).hexdigest() != EXPECTED_SHA256:
        sys.exit('input is not the expected DisciplesGL 2.0.2 C4dll-R.dll; refusing to patch')
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    nsec = struct.unpack_from('<H', data, pe + 6)[0]
    optsz = struct.unpack_from('<H', data, pe + 20)[0]
    opt = pe + 24
    sections = {}
    for i in range(nsec):
        o = opt + optsz + i * 40
        name = data[o:o + 8].rstrip(b'\0').decode()
        vsz, rva, rsz, raw = struct.unpack_from('<IIII', data, o + 8)
        sections[name] = (o, vsz, rva, rsz, raw)
    hdr, vsz, rva, rsz, raw = sections['.text']
    off = lambda r: raw + r - rva

    cave_end = CAVE_RVA + len(CAVE)
    assert rva + vsz <= CAVE_RVA and cave_end <= rva + rsz, 'cave outside .text raw slack'
    assert not any(data[off(CAVE_RVA):off(cave_end)]), 'cave is not empty'
    for site in SITES:
        assert data[off(site):off(site) + len(TAIL)] == TAIL, f'unexpected bytes at {site:#x}'

    for site in SITES:
        rel = CAVE_RVA - (site + 5)
        data[off(site):off(site) + len(TAIL)] = b'\xe9' + struct.pack('<i', rel) + b'\xcc\xcc'
    data[off(CAVE_RVA):off(cave_end)] = CAVE

    new_vsz = cave_end - rva                                    # cover the cave so the loader maps it
    struct.pack_into('<I', data, hdr + 8, new_vsz)
    size_of_code = struct.unpack_from('<I', data, opt + 4)[0]
    struct.pack_into('<I', data, opt + 4, max(size_of_code, (new_vsz + 0x1FF) & ~0x1FF))
    csum_off = opt + 64
    struct.pack_into('<I', data, csum_off, 0)
    struct.pack_into('<I', data, csum_off, checksum(bytes(data), csum_off))

    open(dst, 'wb').write(data)
    print(f'patched {len(SITES)} sites, cave at RVA {CAVE_RVA:#x} ({len(CAVE)} bytes), '
          f'.text VirtualSize {vsz:#x} -> {new_vsz:#x}')
    print('sha256', hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
