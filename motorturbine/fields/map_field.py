from .. import errors, updateset, utils, document
from . import base_field, string_field
import copy


class DictWrapper(dict):
    def __init__(self, *args, dict_field=None, **kwargs):
        self.dict_field = dict_field
        super().__init__(*args, **kwargs)

    def __eq__(self, other):
        return self.as_value() == other

    def update(self, values):
        if values is None:
            return

        self.dict_field.validate(values)
        for key, value in values.items():
            self[key] = value

    def _update(self, values):
        if values is None:
            return

        self.dict_field.validate(values)
        for key, value in values.items():
            field = self.to_field(key, value, sync_field=False)
            dict.__setitem__(self, key, field)

    def __setitem__(self, key, value):
        self.dict_field.validate_key(key)

        field = self.to_field(key, value)

        self.dict_field.pseudo_operators.pop(key, None)
        super().__setitem__(key, field)

    def to_field(self, key, value, sync_field=True):
        name = '{}.{}'.format(self.dict_field.name, key)
        new_field = self.dict_field.value_field.clone(
            document=self.dict_field.document,
            name=name,
            sync_enabled=sync_field)

        old_field = self.get(key, None)
        if old_field is not None:
            new_field.set_value(old_field.get_value())
            new_field.synced()

            # new_field.operators = old_field.operators
        new_field.set_value(value)
        new_field.sync_enabled = True

        return new_field

    def __getitem__(self, index):
        item = super().__getitem__(index)
        if hasattr(item, 'value'):
            item = item.value
        return item

    def __delitem__(self, index):
        item = super().__getitem__(index)

        update = {
            'op': updateset.Unset(index),
            'old_value': item.value
        }
        self.dict_field.pseudo_operators[index] = [update]

        field_name = self.dict_field.name + '.' + index
        self.dict_field.document.update_sync(field_name)
        super().__delitem__(index)

    def as_value(self):
        return {
            name: dict.__getitem__(self, name).get_value()
            for name in self
        }


class MapField(base_field.BaseField):
    """__init__(value_field, key_field=StringField(), *, \
    default={}, required=False, unique=False)

    This field only allows a `dict` type to be set as its value.

    If an entire dict is set instead of singular values each key-value pair in
    the new dict has to match the subfields that were set when initialising
    the field.

    :param BaseField value_field:
        Sets the field type that will be used for the values of the dict.
    """
    def __init__(self,
                 value_field,
                 **kwargs):
        kwargs['default'] = kwargs.pop('default', {})
        super().__init__(**kwargs)
        self.pseudo_operators = {}
        self.key_field = string_field.StringField()
        self.value_field = value_field
        self.value = DictWrapper(dict_field=self)

    def clone(self, *args, **kwargs):
        new_field = super().clone(self.value_field, **kwargs)
        new_field.value.update(self.default)
        return new_field

    def synced(self):
        super().synced()
        self.pseudo_operators = {}

        if self.value is None:
            return

        for name in self.value:
            field = dict.__getitem__(self.value, name)
            field.synced()

    def set_value(self, new_value):
        old_val = None
        if self.value is not None:
            old_val = self.value.copy()

        next_operator = updateset.to_operator(self.value, new_value)
        next_operator.set_original_value(old_val)

        new_value = next_operator.apply()
        self.validate(new_value)

        update = {
            'op': next_operator,
            'old_value': old_val
        }
        if isinstance(next_operator, updateset.Set):
            self.updates = [update]
            self.pseudo_operators = {}
        else:
            self.updates.append(update)

        if new_value is None:
            self.value = new_value
        else:
            self.value.clear()
            self.value._update(new_value)

        if self.sync_enabled:
            self.document.update_sync(self.name)

    def get_updates(self, path):
        if path == '':
            # we need to make sure that if there is a set update on the map
            # each update is actually a value representation of its field
            # instead of the field itself (or document)
            for update in self.updates:
                op = update['op']
                for key in op.update.keys():
                    field = op.update[key]
                    as_field = self.value_field.clone(sync_enabled=False)
                    as_field.set_value(field)
                    op.update[key] = as_field.get_value()

                old = update['old_value']
                for key in old.keys():
                    field = old[key]
                    if isinstance(field, base_field.BaseField):
                        old[key] = field.get_value()

            return self.updates

        sub_path, cutoff = utils.get_sub_path(path, 1)
        name = cutoff[0]

        field = dict.get(self.value, name)

        if field is None:
            return self.pseudo_operators.get(name, [])
        return field.get_updates(sub_path)

    def __getattr__(self, attr):
        path_split = attr.split('.')
        field_name = path_split[0]
        if len(path_split) == 1:
            return super().__getattribute__(attr)

        return self.value[path_split[1]]

    def validate_field(self, value):
        if not isinstance(value, dict):
            raise errors.TypeMismatch(dict, type(value))

        for key, item in value.items():
            self.validate_key(key)

    def validate_key(self, value):
        self.key_field.validate(value)

    def get_value(self):
        if self.value is None:
            return None
        return self.value.as_value()
