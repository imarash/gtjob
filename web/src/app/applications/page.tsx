import Link from "next/link";
import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import {
  Table,
  TableBody,
  TableCell,
  TableColumn,
  TableHeader,
  TableRow,
} from "@/components/base/table/table";
import { ApplicationsView } from "@/components/studio/applications-view";
import { ScoreValue, StatusChip } from "@/components/studio/score";
import { BOARD_COLUMNS } from "@/lib/columns.mjs";
import { loadStudio } from "@/lib/studio-data";

export const instant = false;

export default async function ApplicationsPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string | string[]; view?: string | string[] }>;
}) {
  const params = await searchParams;
  const query = (Array.isArray(params.q) ? params.q[0] : params.q ?? "").trim();
  const viewParam = Array.isArray(params.view) ? params.view[0] : params.view;
  const view = viewParam === "board" ? "board" : "table";
  const { paths, runs, tracker } = await loadStudio();
  const linked = new Set(
    (runs.ok ? runs.runs : [])
      .filter((run) => run.pdfs.length > 0)
      .map((run) => run.slug),
  );

  if (!paths.careerOpsRoot || !tracker) {
    return (
      <Empty
        title="Applications"
        body="Tracking turns on when CAREER_OPS_ROOT is set. Studio does not keep a second list of applications."
      />
    );
  }
  if (!tracker.ok) {
    return <Empty title="Applications" body={tracker.error} path={tracker.path} />;
  }
  if (tracker.missing) {
    return (
      <Empty
        title="Applications"
        body="No tracker file yet. This is an empty list, not a broken one."
        path={tracker.path}
      />
    );
  }

  const needle = query.toLocaleLowerCase();
  const rows = tracker.rows.filter((row) => {
    if (!needle) return true;
    return (
      row.company.toLocaleLowerCase().includes(needle) ||
      row.role.toLocaleLowerCase().includes(needle)
    );
  });

  const table = (
    <Table aria-label="Applications" size="sm">
      <TableHeader>
        <TableColumn isRowHeader>Company</TableColumn>
        <TableColumn>Role</TableColumn>
        <TableColumn>Status</TableColumn>
        <TableColumn>Score</TableColumn>
        <TableColumn>Date</TableColumn>
        <TableColumn>gtjob PDF</TableColumn>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.num} id={row.num}>
            <TableCell>
              <Link href={`/applications/${row.num}`} className="text-body-medium text-text-primary">
                {row.company}
              </Link>
            </TableCell>
            <TableCell>{row.role}</TableCell>
            <TableCell>
              <StatusChip status={row.status} />
            </TableCell>
            <TableCell>
              <ScoreValue score={row.score} />
            </TableCell>
            <TableCell>{row.date}</TableCell>
            <TableCell>{row.runSlug && linked.has(row.runSlug) ? "Linked" : "—"}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );

  const board = (
    <div className="grid gap-4 lg:grid-cols-5">
      {BOARD_COLUMNS.map((column) => {
        const cards = rows.filter((row) => column.states.includes(row.status));
        return (
          <section key={column.id} className="flex flex-col gap-2">
            <h2 className="text-body-medium text-text-primary">
              {column.label}
              <span className="text-text-tertiary"> {cards.length}</span>
            </h2>
            {cards.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-border-button-default px-3 py-6 text-body-2-regular text-text-tertiary">
                None
              </p>
            ) : (
              cards.map((row) => (
                <Link
                  key={row.num}
                  href={`/applications/${row.num}`}
                  className="flex flex-col gap-1 rounded-2xl border border-border-button-default bg-background-secondary-default p-3"
                >
                  <span className="text-body-medium text-text-primary">{row.company}</span>
                  <span className="text-body-2-regular text-text-secondary">{row.role}</span>
                  <ScoreValue score={row.score} />
                </Link>
              ))
            )}
          </section>
        );
      })}
    </div>
  );

  return (
    <>
      <header className="flex flex-col gap-1">
        <h1 className="text-title-2-medium text-text-primary">Applications</h1>
        <p className="text-body-regular text-text-secondary">
          {rows.length} of {tracker.rows.length} from the career-ops tracker.
        </p>
      </header>
      <form method="get" action="/applications" className="flex items-end gap-3">
        <div className="w-full max-w-sm">
          <Input name="q" label="Search" placeholder="Company or role" defaultValue={query} />
        </div>
        {view === "board" ? <input type="hidden" name="view" value="board" /> : null}
        <Button type="submit" variant="secondary">
          Search
        </Button>
      </form>
      {rows.length === 0 ? (
        <p className="rounded-3xl border border-border-button-default bg-background-secondary-default p-6 text-body-regular text-text-secondary">
          {query ? `Nothing matches “${query}”.` : "The tracker has a header and no rows."}
        </p>
      ) : (
        <ApplicationsView view={view} query={query} table={table} board={board} />
      )}
    </>
  );
}

function Empty({ title, body, path }: { title: string; body: string; path?: string }) {
  return (
    <div className="flex flex-col gap-2">
      <h1 className="text-title-2-medium text-text-primary">{title}</h1>
      <p className="rounded-3xl border border-border-button-default bg-background-secondary-default p-6 text-body-regular text-text-secondary">
        {body}
        {path ? (
          <>
            {" "}
            Looked at <span className="text-text-primary">{path}</span>.
          </>
        ) : null}
      </p>
    </div>
  );
}
