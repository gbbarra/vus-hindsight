"""Liga o cenário em português aos passos. Ver auditoria_contaminacao.feature."""
from pytest_bdd import scenarios
from steps.passos_contaminacao import *  # noqa: F403

scenarios("auditoria_contaminacao.feature")
