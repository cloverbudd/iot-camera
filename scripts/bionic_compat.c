// bionic_compat.c — the handful of Android/bionic symbols the vendor .so
// imports that glibc does not provide.
//
// These are all exported from the oracle executable (linked with -rdynamic),
// so the dynamic linker resolves the vendor .so's undefined references
// against the global scope, which is searched before DT_NEEDED libraries.
//
//   fortified string/mem functions -> plain equivalents (the vendor .so is
//     not compiled with _FORTIFY_SOURCE against our libc, so the plain
//     versions are behaviourally identical here)
//   fd_set helpers                 -> glibc equivalents
//   __system_property_get          -> Android system property; stub returns
//     "not found", which is the correct value for a property we don't have
//   android_set_abort_message      -> no-op
//   __sF                           -> bionic's stdout FILE object (data symbol)
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>

char __sF[4096] __attribute__((aligned(16)));

size_t __strlen_chk(const char *s, size_t slen) { (void)slen; return strlen(s); }
void *__memcpy_chk(void *d, const void *s, size_t n, size_t dlen)
{ (void)dlen; return memcpy(d, s, n); }
char *__strcpy_chk(char *d, const char *s, size_t dlen) { (void)dlen; return strcpy(d, s); }
char *__strncpy_chk2(char *d, const char *s, size_t n, size_t dlen)
{ (void)dlen; return strncpy(d, s, n); }
int __vsnprintf_chk(char *s, size_t maxlen, int flag, size_t slen,
                    const char *fmt, __builtin_va_list ap)
{ (void)flag; (void)slen; return vsnprintf(s, maxlen, fmt, ap); }
int __vsprintf_chk(char *s, int flag, size_t slen, const char *fmt,
                   __builtin_va_list ap)
{ (void)flag; (void)slen; return vsprintf(s, fmt, ap); }

void __FD_SET_chk(int fd, fd_set *set) { FD_SET(fd, set); }
void __FD_CLR_chk(int fd, fd_set *set) { FD_CLR(fd, set); }
int  __FD_ISSET_chk(int fd, fd_set *set) { return FD_ISSET(fd, set) ? 1 : 0; }

int __system_property_get(const char *name, char *value)
{
    (void)name;
    if (value) value[0] = '\0';
    return 0; /* length 0 == property not found */
}

void android_set_abort_message(const char *msg) { (void)msg; }

/* bionic's __errno is a TLS int; glibc exposes errno only as a function. */
__thread int __errno = 0;
