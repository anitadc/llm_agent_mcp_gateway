import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      <h1 className="text-3xl font-semibold text-gray-800">404</h1>
      <p className="mt-2 text-gray-500">Page not found.</p>
      <Link to="/" className="mt-4 text-sm text-brand-600 hover:underline">
        Back to dashboard
      </Link>
    </div>
  );
}
