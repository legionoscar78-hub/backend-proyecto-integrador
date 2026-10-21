import pytest

torch = pytest.importorskip("torch")

from app.ml.model import crear_mlp  # noqa: E402


def test_salida_tiene_un_logit_por_clase():
    modelo = crear_mlp(n_entrada=10, n_clases=4, capas=[8, 6], dropout=0.2)
    assert modelo(torch.zeros(5, 10)).shape == (5, 4)


def test_capas_segun_la_configuracion():
    modelo = crear_mlp(n_entrada=10, n_clases=4, capas=[8, 6], dropout=0.2)
    lineales = [m for m in modelo if isinstance(m, torch.nn.Linear)]
    assert [(m.in_features, m.out_features) for m in lineales] == [(10, 8), (8, 6), (6, 4)]


def test_dropout_solo_actua_en_entrenamiento():
    modelo = crear_mlp(n_entrada=10, n_clases=3, capas=[16], dropout=0.5)
    x = torch.ones(4, 10)
    modelo.eval()
    assert torch.equal(modelo(x), modelo(x))


@pytest.mark.parametrize("argumentos", [
    dict(n_entrada=0, n_clases=3, capas=[8], dropout=0.1),
    dict(n_entrada=5, n_clases=1, capas=[8], dropout=0.1),
    dict(n_entrada=5, n_clases=3, capas=[], dropout=0.1),
    dict(n_entrada=5, n_clases=3, capas=[8, 0], dropout=0.1),
    dict(n_entrada=5, n_clases=3, capas=[8], dropout=1.0),
])
def test_rechaza_configuraciones_invalidas(argumentos):
    with pytest.raises(ValueError):
        crear_mlp(**argumentos)
