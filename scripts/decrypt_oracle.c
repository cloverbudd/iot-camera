// decrypt_oracle.c -- call the REAL cs2p2p__P2P_Proprietary_Decrypt function
// directly from the patched vendor .so, with PSK "SHIX", against real
// captured ciphertext. Avoids any hand-reimplementation of the cipher.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>

// mangled name: cs2p2p__P2P_Proprietary_Decrypt(char const*, unsigned char const*, unsigned char*, short)
typedef void (*decrypt_fn)(const char*, const unsigned char*, unsigned char*, short);

int hex2bin(const char* hex, unsigned char* out, int maxlen) {
    int len = strlen(hex) / 2;
    if (len > maxlen) len = maxlen;
    for (int i = 0; i < len; i++) sscanf(hex + 2*i, "%2hhx", &out[i]);
    return len;
}

int main(int argc, char** argv) {
    if (argc < 2) { fprintf(stderr, "usage: %s <ciphertext_hex>\n", argv[0]); return 1; }
    void* h = dlopen("./libapTrans_jni.so", RTLD_NOW);
    if (!h) { fprintf(stderr, "dlopen failed: %s\n", dlerror()); return 1; }
    decrypt_fn fn = (decrypt_fn)dlsym(h, "_Z31cs2p2p__P2P_Proprietary_DecryptPKcPKhPht");
    if (!fn) { fprintf(stderr, "dlsym failed: %s\n", dlerror()); return 1; }

    unsigned char ct[2048];
    int len = hex2bin(argv[1], ct, sizeof(ct));
    unsigned char out[2048] = {0};

    fn("SHIX", ct, out, (short)len);
    for (int i = 0; i < len; i++) printf("%02x", out[i]);
    printf("\n");
    // also print as text (best-effort)
    for (int i = 0; i < len; i++) {
        unsigned char c = out[i];
        putchar((c >= 32 && c < 127) ? c : '.');
    }
    printf("\n");
    return 0;
}
