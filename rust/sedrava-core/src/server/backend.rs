//! First storage abstraction independent of HTTP framing and routing.
//! A bounded, typed commit contract with two opt-in implementations:
//! A3 single-snapshot store, A4 immutable revision journal.
//! Full begin/abort/isolation APIs remain unimplemented (tracker #84).
use super::journal::JournalStore;
use super::sqlite::SqliteStore;
use super::state::Values;
use super::storage::{SaveFailure, Store};
use super::transaction::Ledger;

pub trait TransactionBackend {
    fn commit(
        &mut self,
        proposed: &Values,
        receipts: &Ledger,
    ) -> std::result::Result<(), SaveFailure>;
}
impl TransactionBackend for Store {
    fn commit(
        &mut self,
        proposed: &Values,
        receipts: &Ledger,
    ) -> std::result::Result<(), SaveFailure> {
        self.save_transaction(proposed, receipts)
    }
}
impl TransactionBackend for JournalStore {
    fn commit(
        &mut self,
        proposed: &Values,
        receipts: &Ledger,
    ) -> std::result::Result<(), SaveFailure> {
        self.save_transaction(proposed, receipts)
    }
}

impl TransactionBackend for SqliteStore {
    fn commit(
        &mut self,
        proposed: &Values,
        receipts: &Ledger,
    ) -> std::result::Result<(), SaveFailure> {
        self.save_transaction(proposed, receipts)
    }
}
