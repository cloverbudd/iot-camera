// Stub for Android's liblog.so — the vendor .so only needs __android_log_print.
#include <stdio.h>
#include <stdarg.h>

int __android_log_print(int prio, const char *tag, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "[%s] ", tag ? tag : "?");
    vfprintf(stderr, fmt, ap);
    fprintf(stderr, "\n");
    va_end(ap);
    return 0;
}

int __android_log_write(int prio, const char *tag, const char *msg)
{
    fprintf(stderr, "[%s] %s\n", tag ? tag : "?", msg ? msg : "");
    return 0;
}
