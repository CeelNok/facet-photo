/* Facet.app launcher stub (macOS).
 * A tiny signed Mach-O binary is required: macOS refuses to start unsigned / script-only app bundles.
 * It runs Contents/Resources/launch.sh, which sets up .venv on first start and starts Facet. */
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char *argv[]) {
    char exe[PATH_MAX], real[PATH_MAX], script[PATH_MAX];
    uint32_t size = sizeof(exe);
    if (_NSGetExecutablePath(exe, &size) != 0 || !realpath(exe, real)) return 1;
    char *slash = strrchr(real, '/');               /* …/Facet.app/Contents/MacOS/Facet */
    if (!slash) return 1;
    *slash = '\0';                                  /* …/Facet.app/Contents/MacOS */
    snprintf(script, sizeof(script), "%s/../Resources/launch.sh", real);

    char **args = calloc((size_t)argc + 2, sizeof(char *));
    if (!args) return 1;
    int n = 0;
    args[n++] = "/bin/bash";
    args[n++] = script;
    for (int i = 1; i < argc; i++)
        if (strncmp(argv[i], "-psn_", 5) != 0) args[n++] = argv[i];  /* skip old Finder process ids */
    args[n] = NULL;
    execv("/bin/bash", args);
    perror("Facet launcher");
    return 1;
}
