/*
 * hooktest: run DisciplesGL's animation-speed hook (C4dll-R.dll RVA 0x13080) in isolation.
 *
 *   hooktest.exe <C4dll-R.dll>
 *
 * The DLL is mapped without running DllMain or resolving imports. Its globals are set the way the
 * wrapper sets them at runtime, the hook is called the way the game's patched call reaches it
 * (edx = &step), and then the game's own halvings (0x4f5d60, 0x4f5d71) are applied.
 * Prints every combination and the number that end with step == 0 (the infinite loop).
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>

#define RVA_HOOK 0x13080
#define RVA_ORIG_FN 0x446f0  /* pointer to the game's original 0x61a5fd ("fast" flag) */
#define RVA_GAMESPEED 0x44304
#define RVA_ENABLED 0x44308
#define RVA_REFRESH 0x44310

static unsigned char fake_fast;
static unsigned char fake_original(void) { return fake_fast; }

static unsigned run_hook(void *hook, unsigned step, unsigned char *ret_al)
{
    unsigned eax;
    unsigned *pstep = &step;
    __asm__ volatile("call *%[fn]"
                     : "=a"(eax), "+d"(pstep)
                     : [fn] "D"(hook)
                     : "ecx", "memory", "cc");
    *ret_al = (unsigned char)eax;
    return step;
}

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: %s <C4dll-R.dll>\n", argv[0]);
        return 2;
    }
    HMODULE m = LoadLibraryExA(argv[1], NULL, DONT_RESOLVE_DLL_REFERENCES);
    if (!m) {
        fprintf(stderr, "LoadLibraryEx failed: %lu\n", GetLastError());
        return 1;
    }
    unsigned char *b = (unsigned char *)m;
    void *hook = b + RVA_HOOK;
    *(void **)(b + RVA_ORIG_FN) = (void *)fake_original;

    static const unsigned speeds[] = {14, 30, 52};           /* game's step for speed 1/2/3 */
    static const unsigned refresh[] = {60, 75, 120, 144, 165, 240, 360};
    static const unsigned gamespeed[] = {10, 15, 20, 30};    /* g_Y: 1.0x .. 3.0x (15 = your 1.5x) */
    int zero = 0, total = 0, mismatch = 0;
    for (unsigned en = 0; en <= 1; en++)
        for (int r = 0; r < 7; r++)
            for (int g = 0; g < 4; g++)
                for (int s = 0; s < 3; s++)
                    for (unsigned fast = 0; fast <= 1; fast++)
                        for (unsigned p4 = 0; p4 <= 1; p4++) {
                            *(unsigned *)(b + RVA_ENABLED) = en;
                            *(unsigned *)(b + RVA_REFRESH) = refresh[r];
                            *(unsigned *)(b + RVA_GAMESPEED) = gamespeed[g];
                            fake_fast = (unsigned char)fast;
                            unsigned char al;
                            unsigned step = run_hook(hook, speeds[s], &al);
                            if (al != fast)
                                mismatch++;
                            if (al) step /= 2;   /* game: 0x4f5d60 */
                            if (p4) step /= 2;   /* game: 0x4f5d71 */
                            total++;
                            if (step == 0) {
                                zero++;
                                printf("step=0: enabled=%u refresh=%u gamespeed=%u base=%u fast=%u param_4=%u\n", en,
                                       refresh[r], gamespeed[g], speeds[s], fast, p4);
                            }
                            if (en && refresh[r] == 240 && gamespeed[g] == 15 && s == 0 && fast && p4)
                                printf("YOUR CASE (240 Hz, GameSpeed 1.5x, speed 1, fast, param_4): final step = %u\n",
                                       step);
                        }
    printf("\n%d of %d combinations end with step 0; return-flag mismatches: %d\n", zero, total, mismatch);
    return 0;
}
