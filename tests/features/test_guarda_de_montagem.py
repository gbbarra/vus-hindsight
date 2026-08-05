"""Liga o cenário em português aos passos. Ver guarda_de_montagem.feature."""
from pytest_bdd import scenarios
from steps.passos_montagem import *  # noqa: F403

scenarios("guarda_de_montagem.feature")
