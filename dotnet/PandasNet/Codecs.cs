using Python.Runtime;
using System;
using System.Collections.Generic;

namespace PandasNet
{
    public class Codecs : IPyObjectDecoder, IPyObjectEncoder
    {
        public static Codecs Instance { get; } = new Codecs();

        public static void Initialize(bool force = false) => Instance.Setup(force);

        private bool _isInitialized = false;
        private readonly Dictionary<string, (Type Type, Func<PyObject, object> Decode)> _decoders = new Dictionary<string, (Type, Func<PyObject, object>)>();
        private readonly Dictionary<Type, Func<object, PyObject>> _encoders = new Dictionary<Type, Func<object, PyObject>>();

        private Codecs() 
        {
            Setup(); 
        }

        private void Setup(bool force = false)
        {
            if (_isInitialized && !force) return;
            _isInitialized = true;

            DateTimeCodec.Initialize(this);
            NumpyCodec.Initialize(this);
            PandasCodec.Initialize(this);

            PyObjectConversions.RegisterEncoder(this);
            PyObjectConversions.RegisterDecoder(this);
        }

        public void Register<T>(Func<T, PyObject> encoder) => _encoders[typeof(T)] = p => encoder((T)p);

        public void Register<T>(string pyType, Func<PyObject, T> decoder) => _decoders[pyType] = (typeof(T), p => decoder(p));

        public bool CanDecode(PyType objectType, Type targetType)
        {
            // Decoders typed as object (e.g. numpy arrays) are checked against the target in TryDecode.
            return _decoders.TryGetValue(objectType.ToString(), out var decoder)
                && (decoder.Type == typeof(object) || targetType.IsAssignableFrom(decoder.Type));
        }

        public bool TryDecode<T>(PyObject pyObj, out T value)
        {
            if (_decoders.TryGetValue(pyObj.GetPythonType().ToString(), out var decoder)
                && decoder.Decode(pyObj) is T result)
            {
                value = result;
                return true;
            }

            value = default;
            return false;
        }

        public bool CanEncode(Type type)
        {
            return _encoders.ContainsKey(type);
        }

        public PyObject TryEncode(object value)
        {
            if (value == null) return null; // Todo: Should I return None instead ?

            if (!_encoders.TryGetValue(value.GetType(), out var encoder))
                return null; // Todo: Should I return None instead ?

            return encoder(value);
        }

        public static PyObject Encode(object value) => Instance.TryEncode(value);
    }
}