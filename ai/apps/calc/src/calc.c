#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { char name[32]; double value; } Var;
static const char *src; static size_t pos; static char error_msg[96];
static Var vars[64]; static size_t var_count; static double ans;

static void fail(const char *msg) { if (!error_msg[0]) snprintf(error_msg, sizeof error_msg, "%s", msg); }
static void spaces(void) { while (isspace((unsigned char)src[pos])) pos++; }
static int take(char c) { spaces(); if (src[pos] == c) { pos++; return 1; } return 0; }
static double expr(void);

static double lookup(const char *name, int *found) {
    if (!strcmp(name, "pi")) { *found = 1; return acos(-1.0); }
    if (!strcmp(name, "e")) { *found = 1; return exp(1.0); }
    if (!strcmp(name, "ans")) { *found = 1; return ans; }
    for (size_t i = 0; i < var_count; i++) if (!strcmp(vars[i].name, name)) { *found = 1; return vars[i].value; }
    *found = 0; return 0;
}

static double primary(void) {
    spaces();
    if (take('(')) { double v = expr(); if (!take(')')) fail("unbalanced parenthesis"); return v; }
    if (isdigit((unsigned char)src[pos]) || src[pos] == '.') {
        char *end; double v = strtod(src + pos, &end); if (end == src + pos) { fail("expected number"); return 0; } pos = (size_t)(end - src); return v;
    }
    if (isalpha((unsigned char)src[pos]) || src[pos] == '_') {
        char name[32]; size_t n = 0; while (isalnum((unsigned char)src[pos]) || src[pos] == '_') { if (n + 1 < sizeof name) name[n++] = src[pos]; pos++; } name[n] = 0;
        spaces();
        if (take('(')) {
            double a = expr(), b = 0; int two = take(','); if (two) b = expr(); if (!take(')')) fail("unbalanced parenthesis");
            if (!strcmp(name, "pow") && two) return pow(a, b);
            if (!strcmp(name, "sqrt") && !two) return sqrt(a);
            if (!strcmp(name, "sin") && !two) return sin(a);
            if (!strcmp(name, "cos") && !two) return cos(a);
            if (!strcmp(name, "tan") && !two) return tan(a);
            if (!strcmp(name, "log") && !two) return log(a);
            if (!strcmp(name, "log10") && !two) return log10(a);
            if (!strcmp(name, "exp") && !two) return exp(a);
            if (!strcmp(name, "abs") && !two) return fabs(a);
            if (!strcmp(name, "floor") && !two) return floor(a);
            if (!strcmp(name, "ceil") && !two) return ceil(a);
            fail("unknown function"); return 0;
        }
        int found; double v = lookup(name, &found); if (!found) fail("unknown name"); return v;
    }
    fail("expected expression"); return 0;
}
static double power(void) { double a = primary(); spaces(); if (take('^')) return pow(a, power()); return a; }
static double unary(void) { spaces(); if (take('-')) return -unary(); if (take('+')) return unary(); return power(); }
static double product(void) { double a = unary(); for (;;) { spaces(); if (take('*')) a *= unary(); else if (take('/')) { double b = unary(); if (b == 0) { fail("divide by zero"); return 0; } a /= b; } else if (take('%')) { double b = unary(); if (b == 0) { fail("divide by zero"); return 0; } a = fmod(a, b); } else return a; } }
static double expr(void) { double a = product(); for (;;) { spaces(); if (take('+')) a += product(); else if (take('-')) a -= product(); else return a; } }

static int evaluate(const char *line, double *out) {
    src = line; pos = 0; error_msg[0] = 0; spaces();
    size_t start = pos; char name[32]; size_t n = 0;
    if (isalpha((unsigned char)src[pos]) || src[pos] == '_') { while (isalnum((unsigned char)src[pos]) || src[pos] == '_') { if (n + 1 < sizeof name) name[n++] = src[pos]; pos++; } name[n] = 0; spaces(); }
    if (n && src[pos] == '=') {
        pos++; double value = expr(); spaces(); if (src[pos]) fail("unexpected token");
        if (!error_msg[0]) {
            size_t i;
            for (i = 0; i < var_count && strcmp(vars[i].name, name); i++) {
                /* find an existing variable */
            }
            if (i == var_count && var_count < 64) { snprintf(vars[i].name, sizeof vars[i].name, "%s", name); var_count++; }
            if (i < 64) vars[i].value = value;
            *out = ans = value;
        }
    } else { pos = start; double value = expr(); spaces(); if (src[pos]) fail("unexpected token"); if (!error_msg[0]) *out = ans = value; }
    return error_msg[0] ? 0 : 1;
}
static void print_value(double v) { if (fabs(v - round(v)) < 1e-10 && fabs(v) < 1e15) printf("%.0f\n", v); else printf("%.12g\n", v); }
int main(int argc, char **argv) {
    if (argc > 2) { fprintf(stderr, "usage: calc [expression]\n"); return 2; }
    if (argc == 2) { double v; if (!evaluate(argv[1], &v)) { fprintf(stderr, "error: %s at %zu\n", error_msg, pos); return 1; } print_value(v); return 0; }
    char line[1024]; while (printf("> "), fflush(stdout), fgets(line, sizeof line, stdin)) { if (!strcmp(line, "quit\n") || !strcmp(line, "exit\n")) break; if (!strcmp(line, "help\n")) { puts("expressions: + - * / % ^, functions, variables, ans"); continue; } if (!strcmp(line, "vars\n")) { for (size_t i = 0; i < var_count; i++) printf("%s = ", vars[i].name), print_value(vars[i].value); continue; } double v; if (!evaluate(line, &v)) fprintf(stderr, "error: %s at %zu\n", error_msg, pos); else print_value(v); }
    return 0;
}
