import { Shimmer } from './ui/shimmer';

// Excerpt: the two places the stock template opens a tool step expanded.
  if (isMcpTool) {
    return (
      <McpTool defaultOpen={true}>
        <McpToolHeader />
      </McpTool>
    );
  }

  return (
    <Tool defaultOpen={true}>
      <ToolHeader />
    </Tool>
  );

const MessageToolGroup = ({ tools, isLoading, submitApproval, isSubmitting, pendingApprovalId }) => {
  const isMultiple = tools.length > 1;
  return (
    <div
      className={cn('flex flex-col gap-2', {
        'rounded-md border border-border/60 bg-muted/20 p-2': isMultiple,
      })}
      data-testid={isMultiple ? 'tool-group' : undefined}
    >
      {tools.map((tool) => (
        <ToolPartRenderer
          key={tool.toolCallId}
          part={tool}
          isLoading={isLoading}
          submitApproval={submitApproval}
          isSubmitting={isSubmitting}
          pendingApprovalId={pendingApprovalId}
        />
      ))}
    </div>
  );
};
