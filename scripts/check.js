/*
 * CI's signal that the Worker will still do its job: does neostocks still
 * parse, and does a stock come out the other end?
 *
 * Deliberately hits the live site. The breakage worth catching is neostocks
 * changing shape, and a fixture would hide exactly that.
 */

import { DEFAULT_MIN_PRICE, fetchTarget } from '../src/neostocks.js';

const minPrice = Number(process.env.MIN_PRICE || DEFAULT_MIN_PRICE);

try {
  const t = await fetchTarget({ minPrice });
  console.log(
    `${t.ticker} @ ${t.price} NP  ` +
      `(cheapest of ${t.candidates} at >= ${t.minPrice}, ${t.tracked} tracked)  ` +
      `prices as of ${t.pricesAsOfNst || t.pricesAsOf} NST`
  );
  console.log(`would redirect to ${t.buyUrl}`);
} catch (err) {
  console.error(`check failed: ${err.message}`);
  process.exit(1);
}
