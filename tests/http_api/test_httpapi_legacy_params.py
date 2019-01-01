import pytest
import multidict

from aiosmpp.httpapi.server import WebHandler


async def test_missing_to_param():
    form = multidict.MultiDict()

    with pytest.raises(ValueError) as validation_error:
        WebHandler.parse_legacy_send_post_parameters(form)

    assert 'to address missing' in str(validation_error.value)

    form['to'] = '447428555555'
    with pytest.raises(ValueError) as validation_error:
        WebHandler.parse_legacy_send_post_parameters(form)

    assert 'to address missing' not in str(validation_error.value)


async def test_missing_username_param():
    form = multidict.MultiDict()
    form['to'] = '447428555555'

    with pytest.raises(ValueError) as validation_error:
        WebHandler.parse_legacy_send_post_parameters(form)

    assert 'username missing' in str(validation_error.value)

    form['username'] = 'test'
    with pytest.raises(ValueError) as validation_error:
        WebHandler.parse_legacy_send_post_parameters(form)

    assert 'username missing' not in str(validation_error.value)


async def test_missing_password_param():
    form = multidict.MultiDict()
    form['to'] = '447428555555'
    form['username'] = 'test'

    with pytest.raises(ValueError) as validation_error:
        WebHandler.parse_legacy_send_post_parameters(form)

    assert 'password missing' in str(validation_error.value)

    form['password'] = 'test'
    with pytest.raises(ValueError) as validation_error:
        WebHandler.parse_legacy_send_post_parameters(form)

    assert 'password missing' not in str(validation_error.value)


async def test_missing_content_param():
    form = multidict.MultiDict()
    form['to'] = '447428555555'
    form['username'] = 'test'
    form['password'] = 'test'

    with pytest.raises(ValueError) as validation_error:
        WebHandler.parse_legacy_send_post_parameters(form)

    assert 'content or hex-content' in str(validation_error.value)

    form['content'] = 'test'
    WebHandler.parse_legacy_send_post_parameters(form)


async def test_missing_hex_content_param():
    form = multidict.MultiDict()
    form['to'] = '447428555555'
    form['username'] = 'test'
    form['password'] = 'test'

    with pytest.raises(ValueError) as validation_error:
        WebHandler.parse_legacy_send_post_parameters(form)

    assert 'content or hex-content' in str(validation_error.value)

    form['hex-content'] = 'test'
    WebHandler.parse_legacy_send_post_parameters(form)


async def test_valid_params():
    form = multidict.MultiDict()
    form['to'] = '447428555555'
    form['username'] = 'test'
    form['password'] = 'test'
    form['content'] = 'test'
    form['coding'] = '0'
    form['priority'] = '0'
    form['validity-period'] = '1'
    form['tags'] = '1,2'
    form['dlr'] = 'yes'
    form['dlr-url'] = 'test'
    form['dlr-level'] = '1'
    form['dlr-method'] = 'GET'

    result = WebHandler.parse_legacy_send_post_parameters(form)

    for key in ('to', 'from', 'coding', 'priority', 'sdt', 'validity-period', 'tags', 'content', 'hex-content', 'dlr'):
        assert key in result

    assert isinstance(result['coding'], int)
    assert isinstance(result['priority'], int)
    assert isinstance(result['validity-period'], int)
    for tag in result['tags']:
        assert isinstance(tag, int)

    for key in ('url', 'level', 'method'):
        assert key in result['dlr']


async def test_invalid_coding():
    form = multidict.MultiDict()
    form['to'] = '447428555555'
    form['username'] = 'test'
    form['password'] = 'test'
    form['content'] = 'test'

    form['coding'] = 'test'

    with pytest.raises(ValueError) as validation_error:
        WebHandler.parse_legacy_send_post_parameters(form)

    assert 'coding must be in the range 0-14' in str(validation_error.value)

    form['coding'] = '0'
    # Raise no error
    WebHandler.parse_legacy_send_post_parameters(form)


async def test_invalid_priority():
    form = multidict.MultiDict()
    form['to'] = '447428555555'
    form['username'] = 'test'
    form['password'] = 'test'
    form['content'] = 'test'

    form['priority'] = 'test'

    with pytest.raises(ValueError) as validation_error:
        WebHandler.parse_legacy_send_post_parameters(form)

    assert 'priority must be in the range 0-3' in str(validation_error.value)

    form['priority'] = '0'
    # Raise no error
    WebHandler.parse_legacy_send_post_parameters(form)


async def test_invalid_validity():
    form = multidict.MultiDict()
    form['to'] = '447428555555'
    form['username'] = 'test'
    form['password'] = 'test'
    form['content'] = 'test'

    form['validity-period'] = 'test'

    with pytest.raises(ValueError) as validation_error:
        WebHandler.parse_legacy_send_post_parameters(form)

    assert 'validity-period must be an integer' in str(validation_error.value)

    form['validity-period'] = '-1'

    with pytest.raises(ValueError) as validation_error:
        WebHandler.parse_legacy_send_post_parameters(form)

    assert 'validity-period must be greater than 0' in str(validation_error.value)

    form['validity-period'] = '0'
    # Raise no error
    WebHandler.parse_legacy_send_post_parameters(form)


async def test_invalid_tags():
    form = multidict.MultiDict()
    form['to'] = '447428555555'
    form['username'] = 'test'
    form['password'] = 'test'
    form['content'] = 'test'

    form['tags'] = '12.4'

    with pytest.raises(ValueError) as validation_error:
        WebHandler.parse_legacy_send_post_parameters(form)

    assert 'tags must be integers' in str(validation_error.value)

    form['tags'] = '12,4'

    result = WebHandler.parse_legacy_send_post_parameters(form)
    assert result['tags'] == [12, 4]
