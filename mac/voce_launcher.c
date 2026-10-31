/*
 * Voce LeaderAI - lanciatore del servizio.
 *
 * Resta vivo, avvia "<python> <detta.py> [opzioni]" come figlio e ne segue la sorte.
 * macOS attribuisce microfono, accessibilita' e monitoraggio input all'app che sta
 * sopra il processo: il figlio li eredita, quindi i permessi sono dell'app
 * «Voce LeaderAI» e non di Python o del Terminale.
 *
 * Python e detta.py arrivano dagli argomenti (li scrive il LaunchAgent): l'app non
 * si ricompila a ogni modifica della Voce e i permessi non si perdono.
 * Quando il figlio finisce, esce con lo stesso esito e launchd lo rilancia.
 *
 * Compilazione (la fa `voce riavvia` una volta sola):
 *   clang -O2 -o "Voce LeaderAI" voce_launcher.c
 */
#include <errno.h>
#include <libgen.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

static volatile sig_atomic_t figlio = 0;
static volatile sig_atomic_t ricevuto = 0;

static void inoltra(int segnale) {
    ricevuto = segnale;
    if (figlio > 0) {
        kill((pid_t)figlio, segnale);
    }
}

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "uso: %s <python> <detta.py> [opzioni]\n", argv[0]);
        return 64;
    }

    /* Esegue soltanto un Python con detta.py: l'app non e' un lanciatore di programmi qualsiasi. */
    char *copia_python = strdup(argv[1]);
    char *copia_script = strdup(argv[2]);
    int ammesso = copia_python && copia_script
        && strncmp(basename(copia_python), "python", 6) == 0
        && strcmp(basename(copia_script), "detta.py") == 0;
    if (!ammesso) {
        fprintf(stderr, "%s: accetta solo <python> <detta.py>\n", argv[0]);
        return 64;
    }

    struct sigaction azione;
    memset(&azione, 0, sizeof azione);
    azione.sa_handler = inoltra;
    sigemptyset(&azione.sa_mask);
    sigaction(SIGTERM, &azione, NULL);
    sigaction(SIGINT, &azione, NULL);
    sigaction(SIGHUP, &azione, NULL);

    pid_t pid = 0;
    int errore = posix_spawn(&pid, argv[1], NULL, NULL, &argv[1], environ);
    if (errore != 0) {
        fprintf(stderr, "%s: impossibile avviare %s: %s\n", argv[0], argv[1], strerror(errore));
        return 71;
    }
    figlio = pid;
    if (ricevuto) {
        kill(pid, ricevuto);
    }

    int stato = 0;
    while (waitpid(pid, &stato, 0) < 0) {
        if (errno != EINTR) {
            perror("waitpid");
            return 70;
        }
    }
    if (WIFEXITED(stato)) {
        return WEXITSTATUS(stato);
    }
    if (WIFSIGNALED(stato)) {
        return 128 + WTERMSIG(stato);
    }
    return 70;
}
