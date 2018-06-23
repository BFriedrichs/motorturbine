import pytest
from motorturbine import BaseDocument, fields, errors, connection


@pytest.mark.asyncio
async def test_save(db_config, database):
    connection.Connection.connect(**db_config)
    coll = database['UpdateDoc']

    class UpdateDoc(BaseDocument):
        num1 = fields.IntField()

    doc = UpdateDoc(num1=10)
    await doc.save()

    docs = coll.find()
    assert docs.count() == 1
    assert next(docs)['num1'] == 10

    doc.num1 = 50
    await doc.save()

    docs = coll.find()
    assert docs.count() == 1
    assert next(docs)['num1'] == 50


@pytest.mark.asyncio
async def test_update(db_config, database):
    connection.Connection.connect(**db_config)
    coll = database['UpdateDoc']

    class UpdateDoc(BaseDocument):
        num = fields.IntField()
        num2 = fields.IntField()
    doc = UpdateDoc(num=0)
    await doc.save()

    def set_num(num, limit=0):
        data = coll.find_one()
        new_doc = UpdateDoc(**data)
        new_doc.num = num

        return new_doc.save(limit=limit)

    t1 = set_num(10)
    t2 = set_num(20, limit=1)
    t3 = set_num(30, limit=10)

    await t1
    doc = coll.find_one()
    assert doc['num'] == 10

    with pytest.raises(errors.RetryLimitReached):
        await t2
    doc = coll.find_one()
    assert doc['num'] == 10

    await t3
    doc = coll.find_one()
    eh = coll.find()
    assert doc['num'] == 30


@pytest.mark.asyncio
async def test_repr(db_config, database):
    connection.Connection.connect(**db_config)

    class TestDoc(BaseDocument):
        name = fields.StringField()
        num = fields.IntField()

    result = '<TestDoc {}name=\'Test\' num=15>'
    test = TestDoc(name='Test', num=15)
    assert repr(test) == result.format('')

    await test.save()
    id_str = '_id=ObjectId(\'{}\') '.format(test._id)
    post_save = result.format(id_str)
    assert repr(test) == post_save
