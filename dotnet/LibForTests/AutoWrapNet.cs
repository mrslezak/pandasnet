using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;

namespace LibForTests
{
    // Domain types for auto-wrapped namespaces: enums, settable properties, nested types and static members.
    public enum Liquidity
    {
        Liquid,
        Illiquid,
    }

    public class Position
    {
        public Position(string id, DateTime maturity, Liquidity liquidity)
        {
            Id = id;
            Maturity = maturity;
            Liquidity = liquidity;
        }

        public string Id { get; }
        public DateTime Maturity { get; set; }
        public Liquidity Liquidity { get; }
        public IList<double> Weights { get; set; } = new List<double>();
        public Item Underlying { get; set; }

        public static Position Default => new Position("default", new DateTime(2026, 1, 1), Liquidity.Liquid);

        public string MaturityKind() => Maturity.Kind.ToString();

        public double Value(IPricer pricer) => pricer.Price(Maturity);

        public string Describe(Liquidity liquidity = Liquidity.Illiquid) => liquidity.ToString();

        public class Leg
        {
            public Leg(double notional)
            {
                Notional = notional;
            }

            public double Notional { get; }
        }
    }

    // Interface parameters: callers must pick one of the implementations.
    public interface IPricer
    {
        double Price(DateTime date);
    }

    public class FlatPricer : IPricer
    {
        private readonly double _level;

        public FlatPricer(double level)
        {
            _level = level;
        }

        public double Price(DateTime date) => _level;
    }

    public class ShiftedPricer : IPricer
    {
        private readonly IPricer _inner;
        private readonly double _shift;

        public ShiftedPricer(IPricer inner, double shift)
        {
            _inner = inner;
            _shift = shift;
        }

        public double Price(DateTime date) => _inner.Price(date) + _shift;
    }

    // Parameter named like a Python keyword ("from").
    public class StepPricer : IPricer
    {
        private readonly SortedDictionary<DateTime, double> _steps = new SortedDictionary<DateTime, double>();

        public void Add(DateTime from, double level) => _steps[from] = level;

        public double Price(DateTime date) => _steps.Where(p => p.Key <= date).Select(p => p.Value).LastOrDefault();
    }
}

namespace LibForTests.Auto
{
    public class Portfolio : IEnumerable<Position>
    {
        private readonly List<Position> _positions;

        public Portfolio(IEnumerable<Position> positions)
        {
            _positions = positions.ToList();
        }

        public Position this[int index] => _positions[index];

        public IReadOnlyList<Position> Positions => _positions;

        public double TotalWeight() => _positions.Sum(p => p.Weights.Sum());

        public DateTime LastMaturity(IEnumerable<DateTime> extra) => _positions.Select(p => p.Maturity).Concat(extra).Max();

        public T Echo<T>(T value) => value;

        public IEnumerator<Position> GetEnumerator() => _positions.GetEnumerator();

        IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();
    }
}
