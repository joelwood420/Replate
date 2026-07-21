import styles from './IngredientRow.module.css';

export function IngredientRow({ name, qty }: { name: string; qty: string }) {
  return (
    <div className={styles.row}>
      <div className={styles.name}>{name}</div>
      <div className={styles.qty}>{qty}</div>
    </div>
  );
}
