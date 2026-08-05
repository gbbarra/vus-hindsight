"""Liga o cenário em português aos passos. Ver classificacao_clinvar.feature."""
from pytest_bdd import scenarios
from steps.passos_clinvar import *  # noqa: F403

scenarios("classificacao_clinvar.feature")
